#!/usr/bin/env python
"""Report and enforce agent file ownership.

Every module under ``fabric_iq/`` must be claimed by exactly one agent in
``.github/agents/*.agent.md``, in the "Your Files (You Own These)" section that
precedes the agent's ``## Constraints`` heading. An unclaimed module has no owner
to coach when the preceptorship loop raises a finding against it; a doubly
claimed module has two agents editing the same file.

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

# Backtick-quoted paths such as `fabric_iq/scoring.py` or `fabric_iq/rules/`.
_PATH = re.compile(r"`(fabric_iq/[A-Za-z0-9_./]+)`")
# A reference to another owner is a pointer, not a claim.
_DELEGATED = re.compile(r"owned by \*\*@", re.IGNORECASE)


def package_modules() -> set[str]:
    modules = set()
    for dirpath, _dirnames, filenames in os.walk(PACKAGE_DIR):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            absolute = os.path.join(dirpath, filename)
            modules.add(os.path.relpath(absolute, REPO_ROOT).replace(os.sep, "/"))
    return modules


def _ownership_section(text: str) -> str:
    """Return the part of an agent file that carries ownership claims."""
    head = text.split("## Constraints", 1)[0]
    if "## Your Files" in head:
        head = head.split("## Your Files", 1)[1]
    return head


def claims() -> dict[str, list[str]]:
    """Map module path -> list of agents claiming it."""
    owners: dict[str, list[str]] = {}
    if not os.path.isdir(AGENTS_DIR):
        return owners
    modules = package_modules()
    for filename in sorted(os.listdir(AGENTS_DIR)):
        if not filename.endswith(".agent.md"):
            continue
        agent = filename[: -len(".agent.md")]
        with open(os.path.join(AGENTS_DIR, filename), encoding="utf-8") as handle:
            section = _ownership_section(handle.read())
        for line in section.splitlines():
            if _DELEGATED.search(line):
                continue
            for path in _PATH.findall(line):
                matched = [m for m in modules if m.startswith(path)] if path.endswith("/") else [path]
                for module in matched:
                    if agent not in owners.setdefault(module, []):
                        owners[module].append(agent)
    return owners


def audit() -> tuple[list[str], dict[str, list[str]]]:
    modules = package_modules()
    owners = claims()
    unclaimed = sorted(m for m in modules if not owners.get(m))
    duplicated = {m: a for m, a in sorted(owners.items()) if len(a) > 1 and m in modules}
    return unclaimed, duplicated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="suppress the report")
    args = parser.parse_args()

    unclaimed, duplicated = audit()

    if not args.quiet:
        print(f"Modules under fabric_iq/: {len(package_modules())}")
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

    return 1 if unclaimed or duplicated else 0


if __name__ == "__main__":
    sys.exit(main())
