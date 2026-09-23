#!/usr/bin/env python
"""Evidence-sink hygiene: make Phase 5 release gate criterion 9 executable.

Three questions, answered against the real repository rather than a reviewer's
memory:

1. **Does every writer destination resolve to a committed ignore rule?**
   Every default, every documented output example, and every file extension the
   writers actually emit must be matched by a rule in a tracked ``.gitignore``.
   A destination that is merely *untracked today* becomes tenant evidence in the
   index the first time somebody runs ``git add .`` after a live assessment.

2. **Is any tracked file shadowed by those rules?**
   This is the cost of broad patterns such as ``*.jsonl`` and ``Mart*.csv``. A
   rule wide enough to catch every mart is also wide enough to make a fixture
   invisible: the file stays in the index, but the next contributor's edit is
   silently dropped by ``git add``. Every tracked file must stay trackable.

3. **Does tracked content carry a real identifier?**
   A tenant GUID, a UPN, an email address or an ``onmicrosoft`` host in a
   committed file is tenant-derived evidence that ignore rules cannot recall.
   Only explicitly allowlisted synthetic placeholders pass.

This is a heuristic gate. It reduces, and never replaces, the mandatory pre-push
privacy audit in ``.github/agents/shared.instructions.md``.

Usage:
    python scripts/check_evidence_sinks.py          # report, exit 1 on a problem
    python scripts/check_evidence_sinks.py --quiet  # exit code only
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── what the writers emit ────────────────────────────────────────────────────

#: Gold marts, read from the writer so a new mart cannot skip the gate.
try:  # pragma: no cover - exercised implicitly by every real-tree run
    sys.path.insert(0, REPO_ROOT)
    from fabric_iq.lakehouse import GOLD_TABLES
except ImportError:  # the check must still run outside an importable checkout
    GOLD_TABLES = ("MartRunSummary", "MartObjectReadiness")

#: Silver tables are named after inventory sections.
SILVER_SECTIONS = ("tenant", "workspaces", "semantic_models", "reports", "data_agents")

#: Output flags whose documented values are scanned out of tracked text.
OUTPUT_FLAGS = ("out", "lakehouse", "powerbi", "checkpoint")
_FLAG_EXAMPLE = re.compile(r"--(" + "|".join(OUTPUT_FLAGS) + r")[= ]+([^\s`\"'|)]+)")
#: Only real documentation and code document a command; .gitignore describes rules.
_DOC_SUFFIXES = (".md", ".py", ".yml", ".yaml")

# ── identifier scanning ──────────────────────────────────────────────────────

_GUID = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_TENANT_HOST = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]*\.onmicrosoft\.(?:com|us|de)\b")

#: Reserved, non-routable domains (RFC 2606 / RFC 6761). Anything else is a real
#: mailbox until proven otherwise.
ALLOWED_EMAIL_DOMAINS = frozenset(
    {"example.com", "example.net", "example.org", "example.invalid", "example.test", "invalid"}
)

#: GUIDs that are neither all-placeholder nor tenant-derived, with the reason they
#: are allowed. Empty today: ``tests/test_deployment.py`` uses an obvious
#: placeholder lakehouse id instead of an allowlist entry, which is the preferred
#: fix -- an allowlist entry has to be re-justified by every future reader.
ALLOWED_GUIDS: dict[str, str] = {}

#: Files exempt from the identifier scan, with the reason. Empty by design: an
#: exempt file is a blind spot, and this scanner's own patterns and allowlist do
#: not trip it. Prefer an entry in ALLOWED_GUIDS, which names one value.
ALLOWED_PATHS: dict[str, str] = {}


def _is_placeholder_guid(guid: str) -> bool:
    """True for a GUID no tenant could have issued.

    Two shapes count as obviously synthetic: every dash-separated group is one
    repeated character (``aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee``), or the value
    is zeros with a short counter suffix (``00000000-0000-0000-0000-000000000001``).
    """
    groups = guid.lower().split("-")
    if all(len(set(group)) == 1 for group in groups):
        return True
    return len(guid.lower().replace("-", "").lstrip("0")) <= 2


# ── git plumbing ─────────────────────────────────────────────────────────────


def _git(repo_root: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _unquote(pathname: str) -> str:
    if pathname.startswith('"') and pathname.endswith('"'):
        return pathname[1:-1].encode().decode("unicode_escape")
    return pathname


def check_ignore(repo_root: str, paths: list[str]) -> dict[str, tuple[str, str, str] | None]:
    """Map each path to the ignore rule that matches it, or ``None``.

    The returned rule is ``(source, line, pattern)``. Paths are passed as
    arguments rather than on stdin: git reads stdin verbatim and a Windows CRLF
    would silently defeat an extension pattern such as ``*.pbip``.
    """
    matches: dict[str, tuple[str, str, str] | None] = {path: None for path in paths}
    for start in range(0, len(paths), 200):
        batch = paths[start : start + 200]
        result = _git(repo_root, "check-ignore", "--no-index", "-v", "--non-matching", "--", *batch)
        if result.returncode not in (0, 1):
            raise RuntimeError(f"git check-ignore failed: {result.stderr.strip()}")
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            left, _, pathname = line.partition("\t")
            pathname = _unquote(pathname)
            if left == "::":
                continue
            rest, _, pattern = left.rpartition(":")
            source, _, lineno = rest.rpartition(":")
            matches[pathname] = (source, lineno, pattern)
    return matches


def tracked_files(repo_root: str) -> list[str]:
    result = _git(repo_root, "ls-files")
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


# ── the three checks ─────────────────────────────────────────────────────────


def writer_sinks() -> list[tuple[str, str]]:
    """Every destination a writer can reach, with the reason it must be ignored."""
    run = "20260101T000000Z"
    sinks: list[tuple[str, str]] = [
        ("artifacts/", "--out default folder"),
        (f"artifacts/{run}_assessment.json", "assessment JSON written under --out"),
        (f"artifacts/{run}_backlog.json", "remediation backlog written under --out"),
        (f"artifacts/{run}_backlog.csv", "remediation backlog CSV written under --out"),
        (f"artifacts/{run}_review.json", "preceptorship review written under --out"),
        (f"artifacts/{run}_readiness.html", "HTML report written under --out"),
        ("artifacts/live-checkpoint.json", "--checkpoint documented example (tenant id + Bronze)"),
        ("artifacts/live-checkpoint.json.tmp", "checkpoint write-replace temporary file"),
        # The basenames must be ignored wherever --out is pointed, not only in artifacts/.
        (f"elsewhere/{run}_assessment.json", "assessment JSON under a relocated --out"),
        (f"elsewhere/{run}_backlog.json", "backlog JSON under a relocated --out"),
        (f"elsewhere/{run}_backlog.csv", "backlog CSV under a relocated --out"),
        (f"elsewhere/{run}_review.json", "review JSON under a relocated --out"),
        (f"elsewhere/{run}_readiness.html", "HTML report under a relocated --out"),
        ("lakehouse/", "--lakehouse documented root"),
        (f"lakehouse/bronze/evidence/{run}.jsonl", "Bronze: raw collected payloads"),
        ("powerbi_report/", "--powerbi documented root"),
        ("powerbi_report/data/MartRunSummary.csv", "PBIP mart data folder"),
        ("powerbi_report/IsFabricReadyForIQ.pbip", "generated PBIP project file"),
        ("powerbi_report/IsFabricReadyForIQ.SemanticModel/model.bim", "PBIP model (local paths)"),
        ("powerbi_report/IsFabricReadyForIQ.Report/report.json", "PBIP report definition"),
        # Bare layer folders: the writer's root can be the repository itself.
        (f"bronze/evidence/{run}.jsonl", "Bronze layer at the repository root"),
        (f"silver/workspaces/{run}.jsonl", "Silver layer at the repository root"),
        (f"gold/MartRunSummary/{run}.jsonl", "Gold layer at the repository root"),
        # Extension-level cover for a root this check cannot enumerate.
        (f"elsewhere/{run}.jsonl", "NDJSON mart under an unanticipated lakehouse root"),
        ("elsewhere/IsFabricReadyForIQ.pbip", "PBIP project under an unanticipated root"),
    ]
    for section in SILVER_SECTIONS:
        sinks.append(
            (f"lakehouse/silver/{section}/{run}.jsonl", f"Silver: normalized {section}")
        )
    for table in GOLD_TABLES:
        sinks.append((f"lakehouse/gold/{table}/{run}.jsonl", f"Gold: {table} NDJSON"))
        sinks.append((f"powerbi_report/data/{table}.csv", f"Gold: {table} CSV for Power BI"))
        sinks.append((f"elsewhere/data/{table}.csv", f"Gold: {table} CSV under a relocated root"))
    return sinks


def documented_sinks(repo_root: str) -> list[tuple[str, str]]:
    """Output paths shown in tracked documentation, help text, and workflows.

    A README example is an instruction. If it names a path the ignore rules do
    not cover, the documentation is telling a user to commit tenant evidence.
    """
    found: dict[str, str] = {}
    for path in tracked_files(repo_root):
        if not path.endswith(_DOC_SUFFIXES):
            continue
        absolute = os.path.join(repo_root, path)
        try:
            with open(absolute, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        for flag, value in _FLAG_EXAMPLE.findall(text):
            candidate = value.strip().rstrip(",.;")
            if not candidate or candidate.startswith("-"):
                continue
            # Placeholders, shell expansions, and destinations outside the repo.
            if any(char in candidate for char in "<>${}*") or "://" in candidate:
                continue
            if os.path.isabs(candidate) or candidate.startswith("/") or ":" in candidate:
                continue
            candidate = candidate[2:] if candidate.startswith("./") else candidate
            if not candidate or candidate.startswith(".."):
                continue
            if "." not in os.path.basename(candidate):
                candidate = candidate.rstrip("/") + "/"
            found.setdefault(candidate, f"--{flag} example in {path}")
    return sorted(found.items())


def check_sinks(repo_root: str, sinks: list[tuple[str, str]]) -> list[str]:
    """Report every writer destination that version control would accept."""
    problems: list[str] = []
    matches = check_ignore(repo_root, [path for path, _ in sinks])
    for path, why in sinks:
        rule = matches.get(path)
        if rule is None:
            problems.append(f"{path} - no ignore rule matches ({why})")
            continue
        source, lineno, pattern = rule
        if pattern.startswith("!"):
            problems.append(
                f"{path} - re-included by negation rule {source}:{lineno}:{pattern} ({why})"
            )
        elif os.path.isabs(source) or not source.endswith(".gitignore"):
            problems.append(
                f"{path} - ignored only by {source}, which is not a committed .gitignore ({why})"
            )
    return problems


def check_tracked_not_shadowed(repo_root: str) -> list[str]:
    """Report every tracked file an ignore rule would swallow."""
    problems: list[str] = []
    files = tracked_files(repo_root)
    for path, rule in sorted(check_ignore(repo_root, files).items()):
        if rule is None:
            continue
        source, lineno, pattern = rule
        if pattern.startswith("!"):
            continue  # an explicit re-inclusion is what keeps a fixture trackable
        problems.append(f"{path} - tracked but shadowed by {source}:{lineno}:{pattern}")
    return problems


def scan_tracked_identifiers(
    repo_root: str,
    allowed_guids: dict[str, str] | None = None,
    allowed_domains: frozenset[str] | None = None,
    allowed_paths: dict[str, str] | None = None,
) -> list[str]:
    """Report identifiers in tracked content that are not synthetic placeholders."""
    allowed_guids = ALLOWED_GUIDS if allowed_guids is None else allowed_guids
    allowed_domains = ALLOWED_EMAIL_DOMAINS if allowed_domains is None else allowed_domains
    allowed_paths = ALLOWED_PATHS if allowed_paths is None else allowed_paths
    problems: list[str] = []
    for path in tracked_files(repo_root):
        if path in allowed_paths:
            continue
        absolute = os.path.join(repo_root, path)
        try:
            with open(absolute, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: nothing textual to leak
        for number, line in enumerate(lines, start=1):
            for guid in _GUID.findall(line):
                if _is_placeholder_guid(guid) or guid.lower() in allowed_guids:
                    continue
                problems.append(f"{path}:{number} - GUID {guid} is not a placeholder")
            for host in _TENANT_HOST.findall(line):
                problems.append(f"{path}:{number} - tenant host {host}")
            for address in _EMAIL.findall(line):
                domain = address.rsplit("@", 1)[1].lower()
                if domain in allowed_domains:
                    continue
                problems.append(f"{path}:{number} - address {address} (domain {domain})")
    return problems


def audit(repo_root: str = REPO_ROOT, sinks: list[tuple[str, str]] | None = None) -> dict[str, list[str]]:
    """Run all three checks and return the problems found, by check name."""
    if sinks is None:
        sinks = writer_sinks() + documented_sinks(repo_root)
    return {
        "sinks": check_sinks(repo_root, sinks),
        "shadowed": check_tracked_not_shadowed(repo_root),
        "identifiers": scan_tracked_identifiers(repo_root),
    }


HEADINGS = {
    "sinks": "Writer destinations that version control would accept",
    "shadowed": "Tracked files shadowed by an ignore rule (untrackable edits)",
    "identifiers": "Identifiers in tracked content that are not synthetic",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="suppress the report")
    args = parser.parse_args(argv)

    sinks = writer_sinks() + documented_sinks(REPO_ROOT)
    problems = audit(REPO_ROOT, sinks)

    if not args.quiet:
        print("Evidence-sink hygiene (Phase 5 release gate criterion 9)\n")
        print(f"Writer destinations checked: {len(sinks)}")
        print(f"Tracked files checked:       {len(tracked_files(REPO_ROOT))}")
        for key, heading in HEADINGS.items():
            if problems[key]:
                print(f"\n{heading}:")
                for problem in problems[key]:
                    print(f"  - {problem}")
        if not any(problems.values()):
            print(
                "\nClean: every destination resolves to a committed .gitignore rule, "
                "every tracked file stays trackable, and no tracked identifier is real."
            )

    return 1 if any(problems.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
