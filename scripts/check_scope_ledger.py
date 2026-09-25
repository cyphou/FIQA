#!/usr/bin/env python
"""Make `docs/SCOPE_LEDGER.md` executable (Sprint 7.2).

The ledger records a signed disposition for every element of Fabric's shape this
repository already names in its own code. Until this gate existed the document
was a snapshot: `WORKSPACE_ITEM_KEYS` could gain a fourteenth key and nothing
would notice, which is the exact failure mode the ledger was written to end --
scope that reads identically whether an omission was decided or never seen.

Five questions, answered against the real constants and the real document:

1. **Did the table actually parse?**
   Asked first, and asked loudly. If the row regex silently matches nothing,
   every element looks undisposed *or* -- depending on which direction the code
   reads -- every element looks disposed, and the gate prints success over a
   document it never read. Sprint 5.0.1 found precisely this in
   ``check_agent_ownership.py``, whose path parser could not begin a token with a
   dot and so reported clean over a file it had never opened. The parse check
   therefore asserts a *positive* fact: the number of rows parsed equals the
   number the document's own heading states, and that number is not zero.

2. **Does every declared source still resolve to a non-empty sequence?**
   A source that disappears -- renamed constant, moved module, emptied tuple --
   must never read as "nothing to check". :data:`DECLARED_SOURCES` is the
   explicit list of what this gate is responsible for, and each entry failing to
   load is a failure, not a silence.

3. **Does every element in code carry a disposition?**
   The headline failure mode. Exit 1 naming the element and the agent who must
   triage it.

4. **Does every row still correspond to an element in code?**
   The reverse direction, included deliberately. ``check_agent_ownership.py``
   catches "required but not claimed" and never "claimed but not required", so a
   claim naming a path outside its universe is invisible rather than failing. A
   ledger row for a key that no longer exists is a stale disposition presented as
   a signed one; both directions are checked here so the ledger stays a bijection
   with the source it covers.

5. **Has a dated disposition outlived its review?**
   A ``deliberately excluded`` row must carry a review-by date -- an exclusion
   with no date never comes back and becomes permanent by neglect -- and no dated
   row may sit past that date. See "Why expiry is in this commit" below.

**Why expiry is in this commit.** The sprint calls expiry "the second slice", but
its own validation requires a back-dated-review negative test, and a negative test
cannot exist for a failure mode the gate does not implement. Deferring expiry
would have meant silently dropping a required test, so the review check ships
here. It costs one date comparison over a column the ledger already carries and
the suite already holds to its contract, and it is purely local arithmetic.

**Three things this gate deliberately does not have.**

- **No ``--update``, no ``--accept-all``, no bulk re-dating.** The manual cost on
  every fire is the point. A guard people regenerate without reading is
  decoration, and the ledger says so in its own maintenance section.
- **No network access.** Nothing here opens a socket. A CI gate that fetches a
  vendor page is non-deterministic, breaks the standard-library-only contract and
  fails in the place people trust most. Whether a documented product fact still
  holds is a *human* review obligation, which is what the review-by date is for.
- **No copy of the list it guards.** Every element is imported from the constant
  at call time. A gate holding its own transcription of the thing it guards
  drifts from it, and the drift is invisible in exactly the direction that
  matters: the new key nobody triaged.

Usage:
    python scripts/check_scope_ledger.py            # report, exit 1 on drift
    python scripts/check_scope_ledger.py --quiet    # exit code only
    python scripts/check_scope_ledger.py --ledger P # read P instead of the default

``--ledger`` exists so a test can prove this gate fails on a mutated copy without
touching a document it does not own. It is not an escape hatch: an empty or
unparseable file fails check 1 rather than passing quietly.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import os
import re
import sys
from typing import NamedTuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_PATH = os.path.join(REPO_ROOT, "docs", "SCOPE_LEDGER.md")
LEDGER_RELATIVE = "docs/SCOPE_LEDGER.md"

# Import the constants this gate reconciles from the checkout itself, whatever the
# working directory ``python scripts/check_scope_ledger.py`` was launched from.
# There is deliberately **no fallback copy** of any declared source: where
# ``check_evidence_sinks.py`` keeps a fallback list so it can still run outside an
# importable checkout, this gate must not, because a transcribed copy of the thing
# it guards is exactly the drift it exists to catch. If the import fails, check 2
# fires and names the source -- which is the correct outcome, not a degraded one.
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class Source(NamedTuple):
    """A constant in this repository whose elements the ledger must dispose.

    ``triage`` is the agent named when an element has no row: the ledger owner,
    who must add the row and route the judgement it needs. ``maintainer`` owns
    the constant itself and is named when the source stops loading.
    """

    attribute: str
    module: str
    triage: str
    maintainer: str


#: The agent accountable for this gate; named in the messages that ask for a
#: declaration to be retired rather than a constant restored.
DECLARING_AGENT = "@tester"

#: Everything this gate is responsible for reconciling. One source in this slice,
#: per Sprint 7.2. `TENANT_SETTING_MAP` and `ObjectType` are named in the ledger
#: as *not* covered, and adding either here without its rows would make the gate
#: red on arrival -- they are declared when their rows are written, not before.
DECLARED_SOURCES: tuple[Source, ...] = (
    Source(
        attribute="WORKSPACE_ITEM_KEYS",
        module="fabric_iq.collectors.fabric_api",
        triage="@readme",
        maintainer="@collector",
    ),
)

#: `| 6 | `dataflows` | **deliberately excluded** | reason | `@readme` | 2026-12-24 |`
ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*\*\*([a-z ]+)\*\*\s*\|"
    r"(.*?)\|(.*?)\|(.*?)\|\s*$"
)
#: `## The ledger — `WORKSPACE_ITEM_KEYS`, 13 rows` -- the document states its own
#: row count, so the parse check can assert a positive number rather than merely
#: observing that it found no violations.
SECTION = re.compile(r"^##\s+The ledger\s*[-\u2013\u2014]\s*`([A-Za-z_][A-Za-z0-9_]*)`,\s*(\d+)\s+rows\s*$")
ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

#: Only this disposition is contractually obliged to carry a review-by date; the
#: ledger's own vocabulary table says so ("Must carry: a reason, an owning agent,
#: a review-by date"). Any row of any disposition that *does* carry a date is held
#: to it.
DATED_DISPOSITION = "deliberately excluded"


class LedgerRow(NamedTuple):
    number: int
    key: str
    disposition: str
    basis: str
    owner: str
    review: str


class Section(NamedTuple):
    source: str
    stated_count: int
    rows: list[LedgerRow]


def read_ledger(path: str = LEDGER_PATH) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def parse_sections(text: str) -> list[Section]:
    """Parse each ``## The ledger -- `CONSTANT`, N rows`` block and its rows.

    Rows are attributed to the section that precedes them and collection stops at
    the next ``## `` heading, so the prose tables further down the document (the
    disposition vocabulary, the routed questions, the sources) can never be read
    as dispositions.
    """
    sections: list[Section] = []
    current: Section | None = None
    for line in text.splitlines():
        heading = SECTION.match(line)
        if heading:
            current = Section(heading.group(1), int(heading.group(2)), [])
            sections.append(current)
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is None:
            continue
        row = ROW.match(line)
        if row:
            number, key, disposition, basis, owner, review = row.groups()
            current.rows.append(
                LedgerRow(
                    int(number),
                    key,
                    disposition.strip(),
                    basis.strip(),
                    owner.strip(),
                    review.strip(),
                )
            )
    return sections


def parse_rows(text: str) -> list[LedgerRow]:
    """Every disposition row in the document, across all ledger sections."""
    return [row for section in parse_sections(text) for row in section.rows]


def check_parse(sections: list[Section]) -> list[str]:
    """Non-vacuity guard. Every other check below is quantified over the parse.

    If this returns a problem, no statement this gate could make about the ledger
    is trustworthy -- so it fails rather than reporting on rows it did not find.
    """
    problems: list[str] = []
    if not sections:
        problems.append(
            f"{LEDGER_RELATIVE}: no ledger section parsed -- expected a heading of the form "
            "'## The ledger \u2014 `CONSTANT`, N rows'. The gate cannot tell a disposed "
            "element from an undisposed one and refuses to report clean."
        )
        return problems
    for section in sections:
        if not section.rows:
            problems.append(
                f"{LEDGER_RELATIVE}: section `{section.source}` states {section.stated_count} "
                "rows and parsed 0 -- the table shape changed and every element would look "
                "disposed. @tester must fix the row parser in scripts/check_scope_ledger.py."
            )
        elif len(section.rows) != section.stated_count:
            problems.append(
                f"{LEDGER_RELATIVE}: section `{section.source}` states {section.stated_count} "
                f"rows but {len(section.rows)} parsed -- either the heading is stale or the "
                "parser is reading the table partially."
            )
    return problems


def load_source(source: Source) -> tuple[tuple[str, ...] | None, str | None]:
    """Import a declared source and return ``(elements, problem)``.

    Imported at call time, never transcribed. A missing module, a missing
    attribute or an empty sequence is a *problem*, because a source that
    disappeared must not read as "nothing to check".
    """
    try:
        module = importlib.import_module(source.module)
    except Exception as exc:  # pragma: no cover - exercised via a bogus declaration
        return None, (
            f"declared source `{source.attribute}` is unreadable: cannot import "
            f"{source.module} ({exc.__class__.__name__}: {exc}). A source that disappears "
            f'is not "nothing to check" -- {source.maintainer} must restore it, or '
            f"{DECLARING_AGENT} must retire its declaration in DECLARED_SOURCES."
        )
    if not hasattr(module, source.attribute):
        return None, (
            f"declared source `{source.attribute}` is unreadable: {source.module} has no "
            f'attribute {source.attribute!r}. A source that disappears is not "nothing to '
            f"check\" -- {source.maintainer} must restore it, or {DECLARING_AGENT} must "
            "retire its declaration in DECLARED_SOURCES."
        )
    elements = tuple(getattr(module, source.attribute))
    if not elements:
        return None, (
            f"declared source `{source.attribute}` in {source.module} is empty. An empty "
            f'source reconciles against anything -- {source.maintainer} must restore its '
            f"contents, or {DECLARING_AGENT} must retire its declaration."
        )
    return elements, None


def check_dispositions(source: Source, elements: tuple[str, ...], rows: list[LedgerRow]) -> list[str]:
    """Elements in code with no row -- the failure mode Sprint 7.2 names."""
    disposed = {row.key for row in rows}
    return [
        f"`{source.attribute}` element `{element}` has no disposition in {LEDGER_RELATIVE} -- "
        f"{source.triage} must add a ledger row (the constant is maintained by "
        f"{source.maintainer}). An untriaged row naming the agent who owes the answer is a "
        "valid landing state; a missing row is not."
        for element in elements
        if element not in disposed
    ]


def check_stale_rows(source: Source, elements: tuple[str, ...], rows: list[LedgerRow]) -> list[str]:
    """Rows disposing an element the code no longer names.

    The direction ``check_agent_ownership.py`` structurally cannot see. A
    disposition for a deleted key is not harmless: it reads as a signed decision
    about something that is not there.
    """
    live = set(elements)
    return [
        f"{LEDGER_RELATIVE} row {row.number} disposes `{row.key}`, which `{source.attribute}` "
        f"no longer contains -- {source.triage} must remove the row or {source.maintainer} "
        "must restore the key."
        for row in rows
        if row.key not in live
    ]


def check_reviews(rows: list[LedgerRow], as_of: datetime.date) -> list[str]:
    """Dated dispositions that have outlived their review.

    Two ways a review obligation fails: the date is gone (the exclusion never
    comes back) or the date has passed (nobody came back). Both are reported, and
    neither can be cleared in bulk -- by design, per the ledger's own
    "There is no bulk re-dating command, and there must not be one".
    """
    problems: list[str] = []
    for row in rows:
        match = ISO_DATE.search(row.review)
        if match is None:
            if row.disposition == DATED_DISPOSITION:
                problems.append(
                    f"{LEDGER_RELATIVE} row {row.number} (`{row.key}`) is "
                    f"'{DATED_DISPOSITION}' but carries no yyyy-mm-dd review-by date -- an "
                    "undated exclusion becomes permanent by neglect rather than by decision."
                )
            continue
        try:
            review_by = datetime.date.fromisoformat(match.group(1))
        except ValueError:
            problems.append(
                f"{LEDGER_RELATIVE} row {row.number} (`{row.key}`) carries "
                f"{match.group(1)!r}, which is not a calendar date."
            )
            continue
        if review_by < as_of:
            owner = row.owner or "the owning agent"
            problems.append(
                f"{LEDGER_RELATIVE} row {row.number} (`{row.key}`, {row.disposition}) was due "
                f"for review on {review_by.isoformat()} and today is {as_of.isoformat()} -- "
                f"{owner} must re-verify the reason and its sources and record a new date. "
                "There is no bulk re-dating command and there must not be one."
            )
    return problems


CHECKS = ("parse", "sources", "undisposed", "stale", "expired")

HEADINGS = {
    "parse": "Ledger table did not parse (every check below would be vacuous)",
    "sources": "Declared sources that no longer load",
    "undisposed": "Elements in code with no disposition in the ledger",
    "stale": "Ledger rows disposing an element the code no longer names",
    "expired": "Dispositions past their review-by date",
}


def audit(
    ledger_path: str = LEDGER_PATH,
    as_of: datetime.date | None = None,
    sources: tuple[Source, ...] = DECLARED_SOURCES,
) -> dict[str, list[str]]:
    """Run every check and return the problems found, keyed by check name."""
    as_of = as_of or datetime.date.today()
    problems: dict[str, list[str]] = {name: [] for name in CHECKS}

    try:
        text = read_ledger(ledger_path)
    except OSError as exc:
        problems["parse"].append(f"{ledger_path} could not be read: {exc}")
        return problems

    sections = parse_sections(text)
    problems["parse"] = check_parse(sections)

    by_source = {section.source: section.rows for section in sections}
    all_rows = [row for section in sections for row in section.rows]

    for source in sources:
        elements, failure = load_source(source)
        if failure:
            problems["sources"].append(failure)
            continue
        rows = by_source.get(source.attribute)
        if rows is None:
            problems["sources"].append(
                f"declared source `{source.attribute}` loaded {len(elements)} elements but "
                f"{LEDGER_RELATIVE} has no '## The ledger \u2014 `{source.attribute}`, N rows' "
                f"section -- {source.triage} must add one. An unmentioned source is not a "
                "disposed source."
            )
            continue
        problems["undisposed"].extend(check_dispositions(source, elements, rows))
        problems["stale"].extend(check_stale_rows(source, elements, rows))

    # Review dates are a property of the document, not of any one source, so they
    # are checked over every parsed row even if a source failed to load above.
    problems["expired"] = check_reviews(all_rows, as_of)
    return problems


def count_problems(problems: dict[str, list[str]]) -> int:
    return sum(len(found) for found in problems.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--quiet", action="store_true", help="suppress the report")
    parser.add_argument(
        "--ledger",
        default=LEDGER_PATH,
        help="ledger to read (default: docs/SCOPE_LEDGER.md); for mutation proofs only",
    )
    args = parser.parse_args(argv)

    as_of = datetime.date.today()
    problems = audit(args.ledger, as_of)

    if not args.quiet:
        try:
            relative = os.path.relpath(args.ledger, REPO_ROOT)
        except ValueError:
            # Windows raises when the paths sit on different drives, which is the
            # normal shape of a mutation-proof copy in %TEMP% on a CI runner whose
            # checkout is on another volume.
            relative = os.path.abspath(args.ledger)
        if relative.startswith(".."):  # a mutation-proof copy outside the checkout
            relative = os.path.abspath(args.ledger)
        print("Scope-ledger reconciliation (Sprint 7.2)\n")
        print(f"Ledger:            {relative}")
        print(f"As of:             {as_of.isoformat()}")
        for source in DECLARED_SOURCES:
            elements, failure = load_source(source)
            count = "unreadable" if failure else f"{len(elements)} elements"
            print(f"Declared source:   {source.attribute} ({source.module}) -- {count}")
        try:
            sections = parse_sections(read_ledger(args.ledger))
        except OSError:
            sections = []
        for section in sections:
            print(
                f"Rows parsed:       {len(section.rows)} under `{section.source}` "
                f"(document states {section.stated_count})"
            )
        for name in CHECKS:
            if problems[name]:
                print(f"\n{HEADINGS[name]}:")
                for problem in problems[name]:
                    print(f"  - {problem}")
        if not count_problems(problems):
            print(
                "\nClean: every element of every declared source carries exactly one "
                "disposition, every row names a live element, and no review has expired."
            )

    return 1 if count_problems(problems) else 0


if __name__ == "__main__":
    sys.exit(main())
