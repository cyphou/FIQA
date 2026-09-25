#!/usr/bin/env python
"""Make `docs/SCOPE_LEDGER.md` executable (Sprint 7.2).

The ledger records a signed disposition for every element of Fabric's shape this
repository already names in its own code. Until this gate existed the document
was a snapshot: `WORKSPACE_ITEM_KEYS` could gain a fourteenth key and nothing
would notice, which is the exact failure mode the ledger was written to end --
scope that reads identically whether an omission was decided or never seen.

Six questions, answered against the real constants and the real document:

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
   row may sit past that date. See "Why expiry is in this commit" below. Since
   Sprint 7.3 this question is also asked of the **review calendar** (below).

6. **Does every parsed section name a source this gate declares?**
   Added in Sprint 7.3 after @readme demonstrated the hole while writing the
   review calendar: the parser accepted ``## The ledger -- `TOTALLY_FAKE_CONSTANT`,
   3 rows`` without complaint, printed it as a parsed source, and exited 0. A
   heading naming a constant that does not exist satisfied the parser, so the
   instruction "do not invent a constant to satisfy the parser" was enforced by
   an author's integrity rather than by this gate -- the vacuous-gate pattern
   living inside the anti-drift gate, and the same family as the Sprint 5.0.1
   defect where the ownership parser could not read a dotted path and reported
   clean over a file it had never opened. :func:`check_declared_sections` closes
   it. Note the symmetry: check 2 already fails when a *declared source has no
   section*, so with this the source-to-section mapping is a bijection in both
   directions.

**The review calendar (Sprint 7.3).** ``docs/SCOPE_LEDGER.md`` also carries a
``## The review calendar -- ..., N rows`` section, whose rows watch classes of
Fabric shape that exist **only as prose**: they appear in no constant, no
endpoint and no item key, so no amount of self-reconciliation finds them and the
only mechanism that can is a dated human obligation. Those rows are parsed with
the same row regex, held to the same stated-count assertion, and their dates are
held to the same expiry arithmetic -- and they are deliberately kept **out of**
the source reconciliation, because they dispose no element of any constant and
the undisposed/stale checks are meaningless for them. Their failure text differs
from an exclusion's on purpose: the remedy for an expired exclusion is to
re-justify a reason, and the remedy for an expired calendar row is to re-read the
sources the row names and record a finding, including a nil finding.

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
#: `## The review calendar — classes that exist only as prose, 3 rows` -- the
#: second section kind (Sprint 7.3). Its heading names a human-readable class of
#: Fabric shape rather than a constant, because these rows exist precisely
#: *because* no constant names them. Requiring a backticked identifier here would
#: force a fake constant into the heading, which is the documentation equivalent
#: of a reasonless exclusion and is what check 6 now refuses.
CALENDAR_SECTION = re.compile(
    r"^##\s+The review calendar\s*[-\u2013\u2014]\s*(.+?),\s*(\d+)\s+rows\s*$"
)
ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

#: The two section kinds. ``LEDGER`` rows dispose an element of a declared source
#: and are reconciled against code; ``CALENDAR`` rows dispose nothing and are only
#: ever held to their dates.
LEDGER_KIND = "ledger"
CALENDAR_KIND = "calendar"

#: Only this disposition is contractually obliged to carry a review-by date; the
#: ledger's own vocabulary table says so ("Must carry: a reason, an owning agent,
#: a review-by date"). Any row of any disposition that *does* carry a date is held
#: to it.
DATED_DISPOSITION = "deliberately excluded"

#: The first ``@handle`` in an owner cell. A calendar row's reviewer cell carries
#: both the reviewer *and* the routing for anything the review finds ("`@readme`
#: (accuracy and dating); a change in grounding scope routes to `@scorer` ..."),
#: and splicing that whole cell into the middle of a sentence produced a failure
#: message that read as gibberish. The named reviewer leads; the full cell is
#: quoted at the end, where the routing is what a reviewer needs *after* they find
#: something.
AGENT_HANDLE = re.compile(r"@([a-z][a-z0-9-]*)")

#: How many ``## The review calendar`` sections this gate expects to find, declared
#: here for the same reason :data:`DECLARED_SOURCES` is: so that the thing
#: disappearing is a failure rather than a silence. Wiring the calendar's dates up
#: only to have the section deleted, renamed or typo'd would put the obligations
#: back where Sprint 7.3 found them -- scheduled-looking and never due -- and the
#: gate would stay green through it. A *count* is declared rather than the
#: heading's wording, so @readme can reword the class label freely; retiring the
#: calendar altogether is a deliberate act that costs one edit here, by @tester.
REQUIRED_CALENDAR_SECTIONS = 1


class LedgerRow(NamedTuple):
    number: int
    key: str
    disposition: str
    basis: str
    owner: str
    review: str


class Section(NamedTuple):
    """A parsed ``## `` block of the ledger and the rows beneath it.

    ``source`` is the constant name for a :data:`LEDGER_KIND` section and the
    human-readable class label for a :data:`CALENDAR_KIND` one -- a calendar
    heading names no constant by design. ``kind`` defaults to ``LEDGER_KIND`` so
    the three-argument construction used before Sprint 7.3 still means what it
    did.
    """

    source: str
    stated_count: int
    rows: list[LedgerRow]
    kind: str = LEDGER_KIND

    def describe(self) -> str:
        """How this section is named in a failure message."""
        if self.kind == CALENDAR_KIND:
            return f"review calendar section '{self.source}'"
        return f"section `{self.source}`"


def read_ledger(path: str = LEDGER_PATH) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def parse_sections(text: str) -> list[Section]:
    """Parse every gated section of the ledger and the rows beneath each.

    Two section kinds are recognised, both using the same ``ROW`` regex:

    - ``## The ledger -- `CONSTANT`, N rows`` -- dispositions, reconciled against
      the constant named in the heading.
    - ``## The review calendar -- <class>, N rows`` -- dated human review
      obligations over classes of Fabric shape that exist only as prose. Parsed
      so their dates are enforceable; never reconciled against a constant.

    Rows are attributed to the section that precedes them and collection stops at
    the next ``## `` heading, so the prose tables further down the document (the
    disposition vocabulary, the routed questions, the sources) can never be read
    as dispositions. ``### `` sub-headings deliberately do *not* close a section,
    which is why the review log beneath the calendar was checked against ``ROW``:
    its first column is a date rather than a row number, so it cannot match.
    """
    sections: list[Section] = []
    current: Section | None = None
    for line in text.splitlines():
        heading = SECTION.match(line)
        if heading:
            current = Section(heading.group(1), int(heading.group(2)), [], LEDGER_KIND)
            sections.append(current)
            continue
        calendar = CALENDAR_SECTION.match(line)
        if calendar:
            current = Section(
                calendar.group(1).strip(), int(calendar.group(2)), [], CALENDAR_KIND
            )
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
    """Every *disposition* row in the document, across all ledger sections.

    Calendar rows are excluded, and that exclusion is the contract rather than an
    optimisation: the ledger states in its own prose that ``watched`` "is a review
    obligation, not a scope disposition ... deliberately not one of the four words
    in the disposition vocabulary". Folding calendar rows in here would make the
    document's own tally read 16 instead of 13 and would force the vocabulary
    assertion in ``tests/test_scope_ledger.py`` to admit a fifth word -- which
    would then let a real ledger row be dispositioned ``watched`` and pass. Use
    :func:`parse_calendar_rows` for the other kind.
    """
    return [
        row
        for section in parse_sections(text)
        if section.kind == LEDGER_KIND
        for row in section.rows
    ]


def parse_calendar_rows(text: str) -> list[LedgerRow]:
    """Every review-calendar row in the document."""
    return [
        row
        for section in parse_sections(text)
        if section.kind == CALENDAR_KIND
        for row in section.rows
    ]


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
    calendars = sum(1 for section in sections if section.kind == CALENDAR_KIND)
    if calendars < REQUIRED_CALENDAR_SECTIONS:
        problems.append(
            f"{LEDGER_RELATIVE}: {calendars} review-calendar section(s) parsed and this gate "
            f"declares {REQUIRED_CALENDAR_SECTIONS} -- expected a heading of the form "
            "'## The review calendar \u2014 <class>, N rows'. Its dated obligations would "
            "silently stop coming due, which is worse than never having had them. @readme "
            f"must restore the heading, or {DECLARING_AGENT} must retire "
            "REQUIRED_CALENDAR_SECTIONS."
        )
    for section in sections:
        if not section.rows:
            problems.append(
                f"{LEDGER_RELATIVE}: {section.describe()} states {section.stated_count} "
                "rows and parsed 0 -- the table shape changed and every element would look "
                "disposed. @tester must fix the row parser in scripts/check_scope_ledger.py."
            )
        elif len(section.rows) != section.stated_count:
            problems.append(
                f"{LEDGER_RELATIVE}: {section.describe()} states {section.stated_count} "
                f"rows but {len(section.rows)} parsed -- either the heading is stale or the "
                "parser is reading the table partially."
            )
    return problems


def check_declared_sections(
    sections: list[Section], sources: tuple[Source, ...]
) -> list[str]:
    """Ledger sections naming a constant this gate does not declare.

    The hole @readme found on 2026-09-25 and did not exploit: renaming a heading
    to ``## The ledger -- `TOTALLY_FAKE_CONSTANT`, 3 rows`` parsed cleanly, was
    printed in the report as a parsed source, and exited 0. Nothing anywhere
    checked that a parsed section maps to a *declared* source, so a constant that
    does not exist satisfied the parser in silence -- a vacuous gate inside the
    anti-drift gate.

    Two failure shapes are caught by the same assertion and both matter. The
    invented constant is one. The other is quieter: a real constant added to the
    document and never added to :data:`DECLARED_SOURCES`, whose rows are then
    parsed, counted, expiry-checked and printed while *nothing reconciles them
    against code* -- a section that looks gated and is not.

    Calendar sections are exempt by construction rather than by exception: they
    name a class, never an identifier, and dispose no element of any constant.
    """
    declared = {source.attribute for source in sources}
    return [
        f"{LEDGER_RELATIVE}: section `{section.source}` names a source that is not declared "
        f"in DECLARED_SOURCES, so its {len(section.rows)} row(s) parsed, printed and "
        f"reconciled against nothing. Either `{section.source}` is a constant that exists "
        f"and {DECLARING_AGENT} must declare it (attribute, module, triage and maintainer) "
        f"so its rows are actually checked, or it is not a constant at all and the section "
        "must be retired -- a heading naming a constant that does not exist satisfies the "
        "parser and disposes nothing. A review calendar belongs under "
        "'## The review calendar \u2014 <class>, N rows', which needs no constant."
        for section in sections
        if section.kind == LEDGER_KIND and section.source not in declared
    ]


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


def primary_agent(cell: str, fallback: str) -> str:
    """The first agent named in an owner/reviewer cell, or ``fallback``."""
    match = AGENT_HANDLE.search(cell)
    return f"@{match.group(1)}" if match else (cell.strip() or fallback)


def check_reviews(sections: list[Section], as_of: datetime.date) -> list[str]:
    """Dated obligations that have outlived their review, in both section kinds.

    Two ways a review obligation fails: the date is gone (the obligation never
    comes back) or the date has passed (nobody came back). Both are reported, and
    neither can be cleared in bulk -- by design, per the ledger's own
    "There is no bulk re-dating command, and there must not be one".

    The two kinds fail in different words because they are discharged
    differently. An expired **exclusion** is re-justified: its owner re-states why
    the element stays out of scope and re-dates it. An expired **calendar row** is
    re-*read*: its reviewer opens the public sources the row names, records what
    they found in the review log -- a nil finding is still a finding and is the
    normal outcome -- and re-dates it. A message that told a reviewer to
    re-justify a reason would be pointing at the wrong work.

    Which rows must carry a date also differs. In the ledger only
    ``deliberately excluded`` is contractually dated, because `open` rows are
    tracked by a sprint instead. On the calendar **every** row must be dated: a
    watched class with no date is watched by nobody, and the date is the entire
    mechanism.
    """
    problems: list[str] = []
    for section in sections:
        calendar = section.kind == CALENDAR_KIND
        label = "review calendar row" if calendar else "row"
        for row in section.rows:
            match = ISO_DATE.search(row.review)
            if match is None:
                if calendar:
                    owner = primary_agent(row.owner, "the reviewing agent")
                    problems.append(
                        f"{LEDGER_RELATIVE} {label} {row.number} (`{row.key}`) carries no "
                        "yyyy-mm-dd review-by date -- a watched class with no date is "
                        "watched by nobody, and the date is the whole mechanism. "
                        f"{owner} must set one."
                    )
                elif row.disposition == DATED_DISPOSITION:
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
                    f"{LEDGER_RELATIVE} {label} {row.number} (`{row.key}`) carries "
                    f"{match.group(1)!r}, which is not a calendar date."
                )
                continue
            if review_by < as_of:
                if calendar:
                    reviewer = primary_agent(row.owner, "the reviewing agent")
                    problems.append(
                        f"{LEDGER_RELATIVE} review calendar row {row.number} (`{row.key}`, "
                        f"{row.disposition}) was due for review on {review_by.isoformat()} and "
                        f"today is {as_of.isoformat()} -- {reviewer} must re-read the public "
                        "sources this row names, record what was found in the review log (a nil "
                        "finding is still a finding, and is the normal outcome) and re-date the "
                        "row. This is a watched class, not a dated exclusion: there is no reason "
                        "to re-justify, there are sources to re-read. The row's reviewer cell "
                        f"also states where a finding routes: {row.owner}. There is no bulk "
                        "re-dating command and there must not be one."
                    )
                else:
                    owner = row.owner or "the owning agent"
                    problems.append(
                        f"{LEDGER_RELATIVE} row {row.number} (`{row.key}`, {row.disposition}) was due "
                        f"for review on {review_by.isoformat()} and today is {as_of.isoformat()} -- "
                        f"{owner} must re-verify the reason and its sources and record a new date. "
                        "There is no bulk re-dating command and there must not be one."
                    )
    return problems


CHECKS = ("parse", "sources", "undeclared", "undisposed", "stale", "expired")

HEADINGS = {
    "parse": "Ledger table did not parse (every check below would be vacuous)",
    "sources": "Declared sources that no longer load",
    "undeclared": "Ledger sections naming a source this gate does not declare",
    "undisposed": "Elements in code with no disposition in the ledger",
    "stale": "Ledger rows disposing an element the code no longer names",
    "expired": "Dispositions and watched classes past their review-by date",
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
    problems["undeclared"] = check_declared_sections(sections, sources)

    # Only ledger sections reconcile against a constant. Calendar rows dispose no
    # element of anything -- that is why they exist -- so they are deliberately
    # absent from this mapping; matching them against DECLARED_SOURCES would make
    # the undisposed and stale checks fire on arrival over classes that are not in
    # any constant by definition.
    by_source = {
        section.source: section.rows
        for section in sections
        if section.kind == LEDGER_KIND
    }

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
    # are checked over every parsed section -- both kinds -- even if a source
    # failed to load above.
    problems["expired"] = check_reviews(sections, as_of)
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
            if section.kind == CALENDAR_KIND:
                print(
                    f"Calendar rows:     {len(section.rows)} watched under '{section.source}' "
                    f"(document states {section.stated_count}) -- dates only, no constant"
                )
            else:
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
                "disposition, every section names a declared source, every row names a live "
                "element, and no review -- disposition or watched class -- has expired."
            )

    return 1 if count_problems(problems) else 0


if __name__ == "__main__":
    sys.exit(main())
