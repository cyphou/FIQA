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

#: Top-level folders a writer actually roots its output at. A bare word after an
#: output flag is only a destination if it is one of these; otherwise the flag was
#: being discussed in prose ("--out default folder") rather than demonstrated.
SINK_ROOTS = frozenset({"artifacts", "lakehouse", "powerbi_report", "bronze", "silver", "gold"})

#: Extensions the writers emit. A bare word carrying one of these is a file, not prose.
SINK_SUFFIXES = (".json", ".jsonl", ".csv", ".html", ".pbip", ".bim", ".tmp")


def _is_plausible_destination(candidate: str) -> bool:
    """True when a scraped value can be a filesystem destination rather than prose.

    ``--out`` appears in running text as often as it appears in a command, and the
    regex cannot tell ``--out artifacts`` from ``--out default folder``. Requiring
    one positive signal of a path keeps documentation examples in scope while the
    English word following the flag drops out:

    * a path separator (``artifacts/live-checkpoint.json``, a folder with a
      trailing slash)
    * an explicit relative prefix (``./powerbi_report``)
    * an extension a writer emits (``run.jsonl``)
    * a known writer root (``artifacts``)

    The separator is tested on the *raw* candidate. Stripping first removed the very
    character that proves a path: ``"/" in "results/".strip("/")`` is False, so a
    single-level folder documented with a trailing slash was discarded as prose and
    skipped the whole gate. Only a value that is nothing but separators (``/``)
    names no destination.

    The cost is deliberate: documenting a brand-new *bare* root still requires adding
    it to :data:`SINK_ROOTS` or writing it with a ``./`` prefix, and prose that
    happens to carry a slash (a stray "and/or" after the flag) is now treated as a
    destination. A missed root is silent; a prose word treated as a sink fails the
    gate loudly on every run, which is the direction this check must err in.
    """
    bare = candidate.strip("/\\")
    if not bare:
        return False
    if candidate.startswith("./") or candidate.startswith(".\\"):
        return True
    if "/" in candidate or "\\" in candidate:
        return True
    if bare.lower().endswith(SINK_SUFFIXES):
        return True
    return bare in SINK_ROOTS

# ── identifier scanning ──────────────────────────────────────────────────────

_GUID = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")
#: A tenant id is copied out of the portal dashed and out of a token claim undashed.
#: The boundary excludes a longer hex run, so a 40-hex commit sha never matches.
_GUID_UNDASHED = re.compile(r"(?<![0-9a-zA-Z])[0-9a-fA-F]{32}(?![0-9a-zA-Z])")
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
    """Run git with path quoting disabled, so a non-ASCII path stays usable.

    Under the default ``core.quotePath`` git renders ``docs/café.md`` as the octal
    literal ``"docs/caf\\303\\251.md"``. That literal cannot be opened and matches no
    ignore rule, so such a file was invisible to *both* the shadowing check and the
    identifier scan -- silently, which is the one failure mode this gate exists to
    prevent. ``-c core.quotePath=false`` makes every path round-trip verbatim.
    """
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def check_ignore(repo_root: str, paths: list[str]) -> dict[str, tuple[str, str, str] | None]:
    """Map each path to the ignore rule that matches it, or ``None``.

    The returned rule is ``(source, line, pattern)``. Paths are passed as
    arguments rather than on stdin: git reads stdin verbatim and a Windows CRLF
    would silently defeat an extension pattern such as ``*.pbip``. (``-z`` is not
    an option here -- git rejects it without ``--stdin`` -- so the tab-separated
    form is parsed, and any pathname git echoes back that was not asked for raises
    rather than being dropped into an entry nobody reads.)
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
            if pathname not in matches:
                raise RuntimeError(f"git check-ignore returned an unrequested path: {line!r}")
            if left == "::":
                continue
            rest, _, pattern = left.rpartition(":")
            source, _, lineno = rest.rpartition(":")
            matches[pathname] = (source, lineno, pattern)
    return matches


def tracked_files(repo_root: str) -> list[str]:
    """Every path in the index, NUL-separated so no name can be mangled or lost."""
    result = _git(repo_root, "ls-files", "-z")
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    return [path for path in result.stdout.split("\0") if path.strip()]


def _decode_for_scan(raw: bytes) -> str:
    """Decode tracked bytes for identifier scanning, never raising.

    Skipping anything that is not UTF-8 was a privacy hole: a UTF-16 document is
    textual and leaks exactly like its UTF-8 twin. Every identifier this scanner
    looks for is ASCII, so a lossless byte-preserving fallback loses nothing --
    latin-1 always decodes.

    The NUL strip is separate from the fallback on purpose. A BOM-less UTF-16
    document decodes as UTF-8 *without error* (NUL is a valid UTF-8 byte), so a
    decode-failure-only fallback still missed it; the identifier survived as
    ``7\\x00f\\x003...`` and matched nothing. Dropping NUL bytes puts ASCII runs
    back together in either endianness and leaves newlines, so the reported line
    number still points at the leak. A genuine UTF-8 document has no NUL in it.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text.replace("\x00", "") if "\x00" in text else text


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

    Only values that look like a filesystem destination are kept: the same flag
    appears in prose ("wherever ``--out`` is pointed"), and treating the next
    English word as a folder invents destinations no writer can reach. See
    :func:`_is_plausible_destination`. No file is exempt from the scan -- a real
    example is a real example wherever it is written, including in this script.
    """
    found: dict[str, str] = {}
    for path in tracked_files(repo_root):
        if not path.endswith(_DOC_SUFFIXES):
            continue
        absolute = os.path.join(repo_root, path)
        try:
            with open(absolute, "rb") as handle:
                text = _decode_for_scan(handle.read())
        except OSError:
            continue  # unreadable here, and reported by name by the identifier scan
        for flag, value in _FLAG_EXAMPLE.findall(text):
            candidate = value.strip().rstrip(",.;")
            if not candidate or candidate.startswith("-"):
                continue
            # Placeholders, shell expansions, and destinations outside the repo.
            if any(char in candidate for char in "<>${}*") or "://" in candidate:
                continue
            if os.path.isabs(candidate) or candidate.startswith("/") or ":" in candidate:
                continue
            if not _is_plausible_destination(candidate):
                continue  # prose, not a path
            candidate = candidate[2:] if candidate.startswith("./") else candidate
            if not candidate or candidate.startswith(".."):
                continue
            if "." not in os.path.basename(candidate):
                candidate = candidate.rstrip("/") + "/"
            found.setdefault(candidate, f"--{flag} example in {path}")
    return sorted(found.items())


def check_sinks(repo_root: str, sinks: list[tuple[str, str]]) -> list[str]:
    """Report every writer destination that version control would accept.

    A match is only protection when it comes from a committed ``.gitignore`` *and*
    carries a real pattern. Three ways a match can be worthless:

    * The source is not tracked. ``.git/info/exclude`` protects one clone, and an
      *untracked* ``.gitignore`` is exactly as private -- it can be deleted, or
      simply never exist for a teammate, while this gate reports the tree as safe.
      Checking the filename alone accepted it; the source is now intersected with
      the index.
    * The pattern is blank. A ``.gitignore`` checked out with CRLF endings (git
      stores LF, ``core.autocrlf=true`` writes CRLF) turns every blank line into a
      lone ``\\r``: git reports it as a match, with an empty pattern, for any path
      ending in ``/``. Trusting that match makes this gate vacuous for every
      directory destination on Windows while it still fails honestly on Linux.
    * The pattern is a negation, which re-includes the destination.
    """
    problems: list[str] = []
    tracked = {path.replace("\\", "/") for path in tracked_files(repo_root)}
    matches = check_ignore(repo_root, [path for path, _ in sinks])
    for path, why in sinks:
        rule = matches.get(path)
        if rule is None:
            problems.append(f"{path} - no ignore rule matches ({why})")
            continue
        source, lineno, pattern = rule
        if not pattern.strip():
            problems.append(
                f"{path} - matched only by a blank pattern at {source}:{lineno}, which is not a "
                f"real rule (a CRLF .gitignore matches every directory this way) ({why})"
            )
        elif pattern.startswith("!"):
            problems.append(
                f"{path} - re-included by negation rule {source}:{lineno}:{pattern} ({why})"
            )
        elif (
            os.path.isabs(source)
            or not source.endswith(".gitignore")
            or source.replace("\\", "/") not in tracked
        ):
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
    """Report identifiers in tracked content that are not synthetic placeholders.

    Nothing tracked is skipped for being hard to read. A file that cannot be
    decoded is scanned byte-wise (:func:`_decode_for_scan`); a file that cannot be
    *opened* is reported, because an unscanned file that reports nothing is
    indistinguishable from a clean one.
    """
    allowed_guids = ALLOWED_GUIDS if allowed_guids is None else allowed_guids
    allowed_domains = ALLOWED_EMAIL_DOMAINS if allowed_domains is None else allowed_domains
    allowed_paths = ALLOWED_PATHS if allowed_paths is None else allowed_paths
    problems: list[str] = []
    for path in tracked_files(repo_root):
        if path in allowed_paths:
            continue
        absolute = os.path.join(repo_root, path)
        if os.path.isdir(absolute):
            continue  # a gitlink (submodule): its own checkout runs its own gate
        try:
            with open(absolute, "rb") as handle:
                raw = handle.read()
        except OSError as error:
            problems.append(
                f"{path} - tracked but could not be read "
                f"({type(error).__name__}), so it was never scanned"
            )
            continue
        for number, line in enumerate(_decode_for_scan(raw).splitlines(), start=1):
            for guid in _GUID.findall(line):
                if _is_placeholder_guid(guid) or guid.lower() in allowed_guids:
                    continue
                problems.append(f"{path}:{number} - GUID {guid} is not a placeholder")
            for guid in _GUID_UNDASHED.findall(line):
                if _is_placeholder_guid(guid) or guid.lower() in allowed_guids:
                    continue
                problems.append(f"{path}:{number} - undashed GUID {guid} is not a placeholder")
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
