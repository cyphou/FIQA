#!/usr/bin/env python
"""Report and enforce agent file ownership.

The audited universe is every module under ``fabric_iq/``, every module under
``scripts/``, and :data:`REQUIRED_DOCS`. Each of those paths must be claimed by
exactly one agent in ``.github/agents/*.agent.md``, in the "Your Files (You Own
These)" section that precedes the agent's ``## Constraints`` heading. An
unclaimed module has no owner to coach when the preceptorship loop raises a
finding against it; a doubly claimed module has two agents editing the same file.

``scripts/`` is audited on the same terms as the package, ``__init__.py``
included. An unowned gate is worse than an unowned module: nobody answers for it,
so it degrades into a check that fails open in silence.

The same rule applies to the documentation that makes a privacy, identity,
retention or collection-capability claim, and to the agent-facing Skill
(:data:`REQUIRED_DOCS`, Phase 5 release gate criterion 10). A document that tells
a reader what the tool collects, what it cannot collect, who is named in it, and
how long it is kept is a promise to a customer; a Skill is the same promise made
to a model at prompt time. A promise nobody owns goes stale silently. The required set is explicit rather than inferred: guessing
which file "looks like" a privacy claim would let the gate move on its own.

Usage:
    python scripts/check_agent_ownership.py          # report, exit 1 on drift
    python scripts/check_agent_ownership.py --quiet  # exit code only
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(REPO_ROOT, ".github", "agents")
PACKAGE_DIR = os.path.join(REPO_ROOT, "fabric_iq")

#: Documentation that asserts a privacy, identity, retention or collection-capability
#: claim -- or that a model reads as instruction -- mapped to the agent accountable
#: for it. @security owns no file by design: it audits, it does not maintain.
REQUIRED_DOCS: dict[str, str] = {
    # States what the collectors can and cannot acquire from a live tenant, field by
    # field and endpoint by endpoint. It is a standing claim about the engine's own
    # blind spots: it goes stale the moment a collector gains or loses an endpoint,
    # and a stale row here reads as evidence that was never collectable. Only the
    # agent that owns `fabric_iq/collectors/` can answer for it.
    "docs/API_REALITY_MATRIX.md": "collector",
    # States, per Fabric item type the collector enumerates, whether this repository
    # assesses it -- and when it does not, whether that was decided or merely never
    # noticed. It is a standing claim about collection capability read from the
    # opposite side to the matrix above: not "what can be acquired" but "what, once
    # acquired, is judged". It goes stale the moment `WORKSPACE_ITEM_KEYS` changes,
    # and a stale row reads as a decision that was never made -- which is precisely
    # the failure the ledger was written to end. Only a named owner can answer for
    # that, so the document may never sit unclaimed.
    "docs/SCOPE_LEDGER.md": "readme",
    # Names which identities are read, where they land, and how long they are kept.
    "docs/IDENTITY_AND_RETENTION.md": "readme",
    # Tells an operator how to act on a verdict, and it is the path the console and
    # the HTML report hardcode (fabric_iq.reporting.INTERPRETATION_GUIDE). It is the
    # human-facing home of guidance the Skill only routes to, so if it goes stale or
    # disappears the tool stops standing on its own and every run prints a dead path.
    "docs/INTERPRETING_RESULTS.md": "readme",
    # Tells an operator where evidence is written and which paths stay untracked.
    "docs/INSTALL.md": "orchestrator",
    # Publishes the tool's own readiness evidence and its retention.
    "docs/SELF_ASSESSMENT.md": "preceptor",
    # Deployment surface: workspace items, lakehouse destination, run evidence.
    "fabric/README.md": "orchestrator",
    # A Skill is read by a model as authoritative instruction at prompt time: it
    # states the product limits, the score caps and the coverage floor that the
    # engine owns as constants. Unlike docs/RULES.md it is not generated, so a
    # stale number here contradicts the engine in the one place nobody reviews.
    # tests/test_skill_drift.py holds the values to the constants; this entry
    # holds a named agent to the claim.
    ".github/skills/fabric-iq-readiness/SKILL.md": "readme",
}

# Backtick-quoted repository paths such as `fabric_iq/scoring.py`, `fabric_iq/rules/`,
# `docs/INSTALL.md` or `assess.py`. Restricted to tokens that look like a path -- a
# directory reference, or a source or documentation file -- so that prose in an agent
# file (`getInfo`, `run_id`, `NOT_EVALUATED`) is never mistaken for a claim.
# A leading dot is allowed so that a dot-directory claim such as
# `.github/skills/fabric-iq-readiness/SKILL.md` parses; without it the token was
# read as `github/skills/...` and silently matched nothing.
_PATH = re.compile(r"`(\.?[A-Za-z0-9_][A-Za-z0-9_./-]*)`")
_PATH_LIKE = (".py", ".md")
# A reference to another owner is a pointer, not a claim.
_DELEGATED = re.compile(r"owned by \*\*@", re.IGNORECASE)


def _is_path(token: str) -> bool:
    """True for a backticked token that names a file or directory, not prose.

    A dot-leading token counts only when it carries a path separator: prose about
    the parser itself legitimately writes `.py` and `.md`, and reading a suffix as
    a claim would hand a phantom path to whoever described the rule.
    """
    if token.startswith("."):
        return "/" in token
    return "/" in token or token.endswith(_PATH_LIKE)


def _modules_under(repo_root: str, directory: str) -> set[str]:
    modules = set()
    for dirpath, _dirnames, filenames in os.walk(os.path.join(repo_root, directory)):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            absolute = os.path.join(dirpath, filename)
            modules.add(os.path.relpath(absolute, repo_root).replace(os.sep, "/"))
    return modules


def package_modules(repo_root: str = REPO_ROOT) -> set[str]:
    return _modules_under(repo_root, "fabric_iq")


def script_modules(repo_root: str = REPO_ROOT) -> set[str]:
    """Every ``*.py`` under ``scripts/``, ``__init__.py`` included.

    A gate nobody owns is not a gate: it keeps exiting 0 while the thing it was
    written to catch walks past it, and no agent is accountable for noticing.
    """
    return _modules_under(repo_root, "scripts")


def audited_modules(repo_root: str = REPO_ROOT) -> set[str]:
    """Every source module ownership is enforced over."""
    return package_modules(repo_root) | script_modules(repo_root)


def _ownership_section(text: str) -> str:
    """Return the part of an agent file that carries ownership claims.

    The claim block is "Your Files (You Own These)" up to the next heading. It has
    to end at that heading: later prose legitimately mentions a path it does not
    own (`fabric_iq/` in a reminder about the ownership rule itself), and reading
    a mention as a claim would hand every module to whoever described the rule.
    """
    head = text.split("## Constraints", 1)[0]
    if "## Your Files" in head:
        head = head.split("## Your Files", 1)[1]
        body: list[str] = []
        for line in head.splitlines()[1:]:
            if line.startswith("## "):
                break
            body.append(line)
        return "\n".join(body)
    return head


def claims(
    agents_dir: str = AGENTS_DIR,
    repo_root: str = REPO_ROOT,
    required_docs: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """Map claimed path -> list of agents claiming it."""
    owners: dict[str, list[str]] = {}
    if not os.path.isdir(agents_dir):
        return owners
    if required_docs is None:
        required_docs = REQUIRED_DOCS
    # A directory claim such as `fabric_iq/rules/`, `scripts/` or `fabric/` expands
    # over every path this audit is responsible for.
    universe = audited_modules(repo_root) | set(required_docs)
    for filename in sorted(os.listdir(agents_dir)):
        if not filename.endswith(".agent.md"):
            continue
        agent = filename[: -len(".agent.md")]
        with open(os.path.join(agents_dir, filename), encoding="utf-8") as handle:
            section = _ownership_section(handle.read())
        for line in section.splitlines():
            if _DELEGATED.search(line):
                continue
            for path in _PATH.findall(line):
                if not _is_path(path):
                    continue
                matched = [m for m in universe if m.startswith(path)] if path.endswith("/") else [path]
                for module in matched:
                    if agent not in owners.setdefault(module, []):
                        owners[module].append(agent)
    return owners


def audit(
    agents_dir: str = AGENTS_DIR, repo_root: str = REPO_ROOT
) -> tuple[list[str], dict[str, list[str]]]:
    modules = audited_modules(repo_root)
    owners = claims(agents_dir, repo_root)
    unclaimed = sorted(m for m in modules if not owners.get(m))
    duplicated = {m: a for m, a in sorted(owners.items()) if len(a) > 1 and m in modules}
    return unclaimed, duplicated


def audit_docs(
    agents_dir: str = AGENTS_DIR,
    repo_root: str = REPO_ROOT,
    required_docs: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, list[str]], dict[str, list[str]]]:
    """Audit the documentation that must carry a named accountable owner.

    Returns ``(unclaimed, duplicated, misassigned)``: documents no agent claims,
    documents two agents claim, and documents claimed by an agent other than the
    accountable one named in :data:`REQUIRED_DOCS`.
    """
    if required_docs is None:
        required_docs = REQUIRED_DOCS
    owners = claims(agents_dir, repo_root, required_docs)
    unclaimed = sorted(d for d in required_docs if not owners.get(d))
    duplicated = {d: owners[d] for d in sorted(required_docs) if len(owners.get(d, [])) > 1}
    misassigned = {
        d: owners[d]
        for d in sorted(required_docs)
        if len(owners.get(d, [])) == 1 and owners[d][0] != required_docs[d]
    }
    return unclaimed, duplicated, misassigned


def missing_docs(
    repo_root: str = REPO_ROOT, required_docs: dict[str, str] | None = None
) -> list[str]:
    """Required documents that no longer exist on disk.

    An owner for a file that is gone is not ownership, it is a stale promise --
    and `docs/INTERPRETING_RESULTS.md` is the path the console and the HTML report
    hardcode, so its absence ships a dead pointer to every operator.
    """
    if required_docs is None:
        required_docs = REQUIRED_DOCS
    return sorted(
        doc
        for doc in required_docs
        if not os.path.exists(os.path.join(repo_root, doc.replace("/", os.sep)))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="suppress the report")
    args = parser.parse_args()

    unclaimed, duplicated = audit()
    doc_unclaimed, doc_duplicated, doc_misassigned = audit_docs()
    doc_missing = missing_docs()

    if not args.quiet:
        print(f"Audited modules under fabric_iq/ and scripts/: {len(audited_modules())}")
        if unclaimed:
            print("\nUnclaimed modules (no agent owns these):")
            for module in unclaimed:
                print(f"  - {module}")
        if duplicated:
            print("\nDoubly claimed modules:")
            for module, agents in duplicated.items():
                print(f"  - {module}: {', '.join(agents)}")
        if not unclaimed and not duplicated:
            print("Ownership is clean: every module is claimed exactly once.")

        print(
            "\nDocuments and skills carrying a privacy/identity/retention, "
            f"collection-capability or instruction claim: {len(REQUIRED_DOCS)}"
        )
        if doc_unclaimed:
            print("\nUnclaimed documentation (no agent owns these):")
            for doc in doc_unclaimed:
                print(f"  - {doc}  (accountable owner must be @{REQUIRED_DOCS[doc]})")
        if doc_duplicated:
            print("\nDoubly claimed documentation:")
            for doc, agents in doc_duplicated.items():
                print(f"  - {doc}: {', '.join(agents)}")
        if doc_misassigned:
            print("\nDocumentation claimed by an agent other than the accountable one:")
            for doc, agents in doc_misassigned.items():
                print(f"  - {doc}: claimed by {', '.join(agents)}, expected @{REQUIRED_DOCS[doc]}")
        if doc_missing:
            print("\nRequired documentation that does not exist:")
            for doc in doc_missing:
                print(f"  - {doc}  (accountable owner @{REQUIRED_DOCS[doc]} must restore it)")
        if not (doc_unclaimed or doc_duplicated or doc_misassigned or doc_missing):
            print("Documentation ownership is clean: every required document is claimed once.")

    drifted = bool(
        unclaimed or duplicated or doc_unclaimed or doc_duplicated or doc_misassigned
        or doc_missing
    )
    return 1 if drifted else 0


if __name__ == "__main__":
    sys.exit(main())
