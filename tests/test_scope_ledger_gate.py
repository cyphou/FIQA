"""The scope-ledger gate must be able to fail (Sprint 7.2).

`scripts/check_scope_ledger.py` reconciles the constants this repository names
against the dispositions in `docs/SCOPE_LEDGER.md`. On the real tree it is
silent, and a silent gate is indistinguishable from a broken one until somebody
makes it fire. **A gate that cannot fail is not a gate**, so every failure mode
below is exercised against the real script and the real constant, and the output
it produced is asserted -- not merely its exit code.

The three negative tests Sprint 7.2's validation requires:

(a) :meth:`TestPlantedKey.test_a_new_key_with_no_row_fails_and_is_named`
(b) :meth:`TestExpiredReview.test_a_back_dated_review_fails_and_is_named`
(c) :class:`TestDeclaredSourceDisappears` -- four flavours, because "the source
    is gone" has four shapes and all of them must fail rather than read as
    "nothing to check".

And the two Sprint 7.3 added, both reproduced against the real script before the
code moved:

(d) :class:`TestTheReviewCalendarIsGated` -- a back-dated review-calendar row used
    to exit 0 and print "Clean", because ``parse_sections()`` only collected rows
    under a ``## The ledger -- `CONSTANT`, N rows`` heading. An obligation twenty
    months overdue reported as fine. **A review obligation that silently never
    comes due is worse than none, because it looks scheduled.**
(e) :class:`TestASectionMustNameADeclaredSource` -- the parser accepted a section
    naming a constant that does not exist, printed it as a parsed source and
    exited 0. Nothing checked that a parsed section mapped to a *declared* source,
    so "do not invent a constant to satisfy the parser" was enforced by an
    author's integrity rather than by this gate. That is the vacuous-gate pattern
    living inside the anti-drift gate.

And the trap (c) exists to protect against, tested directly in
:class:`TestTheParseCannotBeVacuous`: if the row regex silently matches nothing,
every element looks disposed and the gate prints success over a document it never
read. That is what Sprint 5.0.1 found in ``check_agent_ownership.py``, whose path
parser could not begin a token with a dot and so reported clean over a file it had
never opened. The gate asserts a positive parse -- rows found equals rows the
document states -- and so does this suite.

**`docs/SCOPE_LEDGER.md` belongs to @readme and is never written by these tests.**
Every document-side mutation is made to a copy in a temporary directory and read
through ``--ledger``; :meth:`TestTheRealLedgerIsNeverMutated` re-reads the real
file's bytes afterwards and proves they are unchanged.
"""

import ast
import contextlib
import datetime
import hashlib
import io
import os
import re
import shutil
import tempfile
import unittest

from scripts.check_scope_ledger import (
    CALENDAR_KIND,
    DECLARED_SOURCES,
    LEDGER_KIND,
    LEDGER_PATH,
    REQUIRED_CALENDAR_SECTIONS,
    Source,
    audit,
    count_problems,
    load_source,
    main,
    parse_calendar_rows,
    parse_rows,
    parse_sections,
    read_ledger,
)
from tests.helpers import REPO_ROOT

SCRIPT = os.path.join(REPO_ROOT, "scripts", "check_scope_ledger.py")


def imported_modules():
    """Every module the gate actually imports, read from its parse tree.

    Deliberately `ast` rather than a regex over the source. The regex this
    replaced -- ``^\\s*(?:import|from)\\s+(\\w+)`` -- matched the *prose* of the
    module docstring the moment a wrapped sentence began with the word "from",
    and reported a dependency on a module named `an`. A dependency check that can
    be tripped by an English sentence is a check nobody will believe the third
    time it fires, and the fix is to read imports exactly rather than to loosen
    what counts as one: both assertions below got stricter, not laxer.
    """
    with open(SCRIPT, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=SCRIPT)
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules.append(node.module)
    assert modules, "no import parsed -- the check would be vacuous"
    return modules


def run(argv):
    """Invoke the CLI in-process; return ``(exit_code, stdout)``."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


@contextlib.contextmanager
def ledger_copy(text):
    """Write ``text`` to a temporary ledger and yield its path.

    ``newline=""`` keeps the bytes as they were read. The real document is
    checked out CRLF on Windows, and a copy silently renormalised to LF would
    stop these proofs from exercising the line endings CI actually sees -- the
    same class of defect that made a CRLF `.gitignore` parse as an empty pattern.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = os.path.join(tmp, "SCOPE_LEDGER.md")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        yield path


@contextlib.contextmanager
def mutated_ledger(*replacements):
    """Yield the path to a copy of the ledger with ``(old, new)`` applied.

    The real document is @readme's and is opened read-only. Every proof below
    mutates a temporary copy, which is also the only way to prove the gate fires
    on a document-side defect without committing one.
    """
    text = read_ledger(LEDGER_PATH)
    for old, new in replacements:
        assert old in text, f"the mutation anchor {old!r} is no longer in the ledger"
        text = text.replace(old, new, 1)
    with ledger_copy(text) as path:
        yield path


@contextlib.contextmanager
def source_attribute(module, name, value, delete=False):
    """Temporarily replace or remove a constant on an imported module."""
    original = getattr(module, name)
    try:
        if delete:
            delattr(module, name)
        else:
            setattr(module, name, value)
        yield
    finally:
        setattr(module, name, original)


CALENDAR_HEADING = "## The review calendar \u2014 classes that exist only as prose, 3 rows"


def calendar_row_line(number):
    """Return ``(row, line)`` for a calendar row, asserting the line is unique.

    Every calendar row carries the same ``2026-12-24``, and so do five ledger
    rows, so the blunt ``replace(date)`` the exclusion proofs use cannot target
    one calendar row. Anchoring on the whole line keeps the mutation precise and
    makes the proof fail loudly if @readme renumbers or renames a row rather than
    silently mutating nothing.
    """
    text = read_ledger(LEDGER_PATH)
    row = next(r for r in parse_calendar_rows(text) if r.number == number)
    prefix = f"| {number} | `{row.key}` |"
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1, f"expected exactly one line starting {prefix!r}, got {len(lines)}"
    return row, lines[0]


def redated_calendar_row(number, new_date):
    """A ``(old, new)`` replacement moving one calendar row's review-by date."""
    row, line = calendar_row_line(number)
    old_tail = f"| {row.review} |"
    assert line.rstrip().endswith(old_tail), line[-40:]
    head, tail = line.rsplit(old_tail, 1)
    return line, f"{head}| {new_date} |{tail}"


class TestTheGateIsSilentOnTheRealTree(unittest.TestCase):
    def test_the_real_tree_reconciles_and_exits_zero(self):
        problems = audit()
        self.assertEqual(
            count_problems(problems), 0, f"the real tree does not reconcile: {problems}"
        )
        code, output = run([])
        self.assertEqual(code, 0)
        self.assertIn("Clean:", output)

    def test_the_report_states_what_it_checked(self):
        # A gate that prints "clean" without saying over what is asking to be
        # trusted rather than read.
        _code, output = run([])
        self.assertIn("WORKSPACE_ITEM_KEYS", output)
        self.assertIn("13 elements", output)
        self.assertIn("Rows parsed:       13", output)
        # ...including the section kind that reconciles against no constant, so a
        # calendar silently dropping out of the parse is visible in the report.
        self.assertIn("Calendar rows:     3", output)
        self.assertIn("dates only, no constant", output)


class TestTheParseCannotBeVacuous(unittest.TestCase):
    """The trap: a parser that matches nothing while the gate reports success."""

    def test_the_parse_finds_the_number_of_rows_the_document_states(self):
        sections = parse_sections(read_ledger(LEDGER_PATH))
        ledgers = [s for s in sections if s.kind == LEDGER_KIND]
        calendars = [s for s in sections if s.kind == CALENDAR_KIND]
        # Coupled to Sprint 7.3: before the calendar was gated this asserted
        # exactly one section. Two kinds now parse, and each is still held to the
        # count its own heading states.
        self.assertEqual(len(ledgers), 1, "expected exactly one ledger section")
        self.assertEqual(len(calendars), REQUIRED_CALENDAR_SECTIONS)
        for section in sections:
            with self.subTest(section=section.source):
                self.assertEqual(
                    len(section.rows),
                    section.stated_count,
                    "rows parsed must equal the count the heading states, or the gate is "
                    "reporting over a table it only partially read",
                )
                self.assertTrue(section.rows, "a section parsing zero rows is a vacuous one")
        self.assertEqual(ledgers[0].source, "WORKSPACE_ITEM_KEYS")
        self.assertEqual(len(ledgers[0].rows), 13)
        self.assertEqual(len(calendars[0].rows), 3)

    def test_the_parsed_rows_are_a_bijection_with_the_live_constant(self):
        # The assertion tests/test_scope_ledger.py deliberately left to this
        # sprint: 13 rows, 13 keys, one row per key and one key per row.
        from fabric_iq.collectors.fabric_api import WORKSPACE_ITEM_KEYS

        keys = [row.key for row in parse_rows(read_ledger(LEDGER_PATH))]
        self.assertEqual(sorted(keys), sorted(WORKSPACE_ITEM_KEYS))
        self.assertEqual(len(keys), len(set(keys)), "a key carries two rows")

    def test_a_table_that_stops_matching_the_row_shape_fails_rather_than_passing(self):
        # Strip the backticks off every item key: the rows are still visibly a
        # table to a human, and invisible to the parser. A gate quantified over
        # "for every row" would now check nothing and print success.
        text = read_ledger(LEDGER_PATH)
        broken = re.sub(r"^\|(\s*\d+\s*)\|\s*`([^`]+)`", r"|\1| \2", text, flags=re.MULTILINE)
        self.assertNotEqual(broken, text, "the mutation changed nothing")
        with ledger_copy(broken) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])

        self.assertEqual(code, 1)
        self.assertTrue(problems["parse"], "an unparseable table must be reported")
        self.assertIn("parsed 0", output)
        self.assertNotIn("Clean:", output)

    def test_a_stale_row_count_in_the_heading_fails(self):
        with mutated_ledger(
            ("`WORKSPACE_ITEM_KEYS`, 13 rows", "`WORKSPACE_ITEM_KEYS`, 12 rows")
        ) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])
        self.assertEqual(code, 1)
        self.assertTrue(problems["parse"])
        self.assertIn("states 12 rows but 13 parsed", output)

    def test_the_prose_tables_are_never_read_as_dispositions(self):
        # The document carries a disposition vocabulary table, a routed-questions
        # table and a sources table. A parser loose enough to read those would
        # manufacture dispositions for keys nobody signed.
        keys = {row.key for row in parse_rows(read_ledger(LEDGER_PATH))}
        for intruder in ("TENANT_SETTING_MAP", "Q1", "assessed"):
            self.assertNotIn(intruder, keys)


class TestPlantedKey(unittest.TestCase):
    """(a) Plant a new key in the enumerated source -> exit 1 naming it."""

    def test_a_new_key_with_no_row_fails_and_is_named(self):
        from fabric_iq.collectors import fabric_api

        planted = fabric_api.WORKSPACE_ITEM_KEYS + ("MirroredDatabase",)
        with source_attribute(fabric_api, "WORKSPACE_ITEM_KEYS", planted):
            problems = audit()
            code, output = run([])

        self.assertEqual(code, 1)
        self.assertEqual(len(problems["undisposed"]), 1, problems["undisposed"])
        message = problems["undisposed"][0]
        self.assertIn("MirroredDatabase", message)
        self.assertIn("WORKSPACE_ITEM_KEYS", message)
        self.assertIn("docs/SCOPE_LEDGER.md", message)
        # "exit 1 naming the element and the agent who must triage it"
        self.assertIn("@readme", message)
        self.assertIn("MirroredDatabase", output)
        self.assertNotIn("Clean:", output)

    def test_the_gate_recovers_when_the_key_is_removed_again(self):
        # Proves the planted-key proof above is a real mutation of the real
        # constant rather than a copy the gate never consulted.
        self.assertEqual(count_problems(audit()), 0)

    def test_the_gate_holds_no_transcribed_copy_of_the_source(self):
        # "Import the constant; never re-type the list." A fallback copy would
        # keep the gate green through exactly the change it exists to catch.
        from fabric_iq.collectors import fabric_api

        source = DECLARED_SOURCES[0]
        with open(SCRIPT, encoding="utf-8") as handle:
            script = handle.read()
        for key in fabric_api.WORKSPACE_ITEM_KEYS:
            self.assertNotIn(
                f'"{key}"',
                script,
                f"{key!r} is transcribed into the gate; it must be imported instead",
            )
        elements, failure = load_source(source)
        self.assertIsNone(failure)
        self.assertEqual(elements, tuple(fabric_api.WORKSPACE_ITEM_KEYS))


class TestUndisposedFromTheDocumentSide(unittest.TestCase):
    """The same failure reached by deleting the row instead of adding the key."""

    def test_deleting_a_row_leaves_its_key_undisposed(self):
        text = read_ledger(LEDGER_PATH)
        kept = [line for line in text.splitlines(True) if "| `GraphModel` |" not in line]
        self.assertEqual(
            len(text.splitlines(True)) - len(kept), 1, "expected exactly one GraphModel row"
        )
        shortened = "".join(kept).replace(
            "`WORKSPACE_ITEM_KEYS`, 13 rows", "`WORKSPACE_ITEM_KEYS`, 12 rows", 1
        )
        with ledger_copy(shortened) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])
        self.assertEqual(code, 1)
        self.assertEqual(problems["parse"], [])
        self.assertEqual(len(problems["undisposed"]), 1)
        self.assertIn("GraphModel", problems["undisposed"][0])
        self.assertIn("@readme", output)

    def test_a_row_for_a_key_the_code_no_longer_names_fails(self):
        # The direction check_agent_ownership.py structurally cannot see:
        # "claimed but not required" is invisible there, and a stale signed
        # disposition is not harmless.
        from fabric_iq.collectors import fabric_api

        shrunk = tuple(k for k in fabric_api.WORKSPACE_ITEM_KEYS if k != "Notebook")
        with source_attribute(fabric_api, "WORKSPACE_ITEM_KEYS", shrunk):
            problems = audit()
            code, output = run([])
        self.assertEqual(code, 1)
        self.assertEqual(len(problems["stale"]), 1, problems["stale"])
        self.assertIn("Notebook", problems["stale"][0])
        self.assertIn("no longer contains", output)


class TestExpiredReview(unittest.TestCase):
    """(b) Back-date a disposition past its review date -> exit 1."""

    def test_a_back_dated_review_fails_and_is_named(self):
        with mutated_ledger(("| 2026-12-24 |", "| 2020-01-01 |")) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])

        self.assertEqual(code, 1)
        self.assertEqual(len(problems["expired"]), 1, problems["expired"])
        message = problems["expired"][0]
        self.assertIn("2020-01-01", message)
        self.assertIn("dataflows", message)
        self.assertIn("@readme", message)
        self.assertIn("row 6", message)
        self.assertIn("There is no bulk re-dating command", output)

    def test_an_exclusion_that_loses_its_date_fails(self):
        # An undated exclusion never comes back for review: it becomes permanent
        # by neglect rather than by decision, which is the failure-open shape.
        with mutated_ledger(("| 2026-12-24 |", "| n/a |")) as path:
            problems = audit(path)
            code, _output = run(["--ledger", path])
        self.assertEqual(code, 1)
        self.assertEqual(len(problems["expired"]), 1, problems["expired"])
        self.assertIn("carries no yyyy-mm-dd review-by date", problems["expired"][0])

    def test_a_date_still_in_the_future_is_silent(self):
        # The counterpart assertion: expiry must fire on the date, not on the
        # presence of a date. Otherwise every exclusion is permanently red and
        # the gate gets switched off.
        future = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        with mutated_ledger(("| 2026-12-24 |", f"| {future} |")) as path:
            self.assertEqual(count_problems(audit(path)), 0)

    def test_expiry_is_measured_against_today_not_a_frozen_constant(self):
        # audit(as_of=...) exists for this assertion only; the CLI never exposes
        # a date override, because a flag that moves "today" is a flag that
        # silences the review obligation.
        past = datetime.date(2027, 1, 1)
        self.assertTrue(audit(LEDGER_PATH, as_of=past)["expired"])
        self.assertEqual(audit(LEDGER_PATH, as_of=datetime.date(2026, 1, 1))["expired"], [])


class TestDeclaredSourceDisappears(unittest.TestCase):
    """(c) Remove a declared source entirely -> exit 1.

    A source that disappears must never read as "nothing to check". Four shapes,
    because the constant can vanish in four ways and each one of them would
    otherwise leave the gate quantified over an empty set and printing success.
    """

    def test_a_missing_constant_fails_rather_than_reporting_clean(self):
        from fabric_iq.collectors import fabric_api

        with source_attribute(fabric_api, "WORKSPACE_ITEM_KEYS", None, delete=True):
            problems = audit()
            code, output = run([])

        self.assertEqual(code, 1)
        self.assertEqual(len(problems["sources"]), 1, problems["sources"])
        message = problems["sources"][0]
        self.assertIn("WORKSPACE_ITEM_KEYS", message)
        self.assertIn("is unreadable", message)
        self.assertIn("@collector", message)
        self.assertIn('is not "nothing to check"', message)
        self.assertEqual(problems["undisposed"], [], "an unreadable source reports once")
        self.assertNotIn("Clean:", output)
        self.assertIn("unreadable", output)

    def test_an_emptied_constant_fails_rather_than_reconciling_with_anything(self):
        from fabric_iq.collectors import fabric_api

        with source_attribute(fabric_api, "WORKSPACE_ITEM_KEYS", ()):
            problems = audit()
            code, _output = run([])
        self.assertEqual(code, 1)
        self.assertEqual(len(problems["sources"]), 1)
        self.assertIn("is empty", problems["sources"][0])

    def test_a_declaration_pointing_at_a_module_that_is_gone_fails(self):
        gone = Source(
            attribute="WORKSPACE_ITEM_KEYS",
            module="fabric_iq.collectors.fabric_api_renamed",
            triage="@readme",
            maintainer="@collector",
        )
        problems = audit(LEDGER_PATH, sources=(gone,))
        self.assertEqual(len(problems["sources"]), 1, problems["sources"])
        self.assertIn("cannot import", problems["sources"][0])
        self.assertIn("@collector", problems["sources"][0])

    def test_a_source_the_ledger_never_mentions_fails(self):
        # The declaration survives and the constant loads, but the document has
        # no section for it. Silence here would mean a source is "covered"
        # because nobody wrote it down.
        with mutated_ledger(
            ("## The ledger — `WORKSPACE_ITEM_KEYS`, 13 rows", "## The ledger — `RENAMED_KEYS`, 13 rows")
        ) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])
        self.assertEqual(code, 1)
        self.assertTrue(problems["sources"])
        self.assertIn("has no '## The ledger", problems["sources"][0])
        self.assertIn("@readme", output)

    def test_an_empty_declaration_list_is_not_a_pass(self):
        # Defensive: if someone empties DECLARED_SOURCES the gate would be
        # trivially green, so the declaration list itself is asserted non-empty.
        self.assertTrue(DECLARED_SOURCES, "the gate must declare at least one source")
        self.assertEqual(
            [s.attribute for s in DECLARED_SOURCES],
            ["WORKSPACE_ITEM_KEYS"],
            "Sprint 7.2 covers one source; adding another needs its ledger section first",
        )


class TestTheReviewCalendarIsGated(unittest.TestCase):
    """(d) Sprint 7.3: the review calendar's dates must actually come due.

    Before this slice, `parse_sections()` collected rows only under
    ``## The ledger -- `CONSTANT`, N rows``, so the calendar section was never
    parsed and `check_reviews()` never saw its rows. Reproduced on 2026-09-25 by
    back-dating calendar row 1 to `2025-01-01` and running the real script
    against the copy: exit 0, "Clean" -- an obligation twenty months overdue
    reported as fine. **A review obligation that silently never comes due is
    worse than none, because it looks scheduled.**
    """

    def test_the_calendar_parses_as_its_own_kind_and_is_not_vacuous(self):
        rows = parse_calendar_rows(read_ledger(LEDGER_PATH))
        self.assertTrue(rows, "no calendar row parsed -- the dates are unenforced again")
        for row in rows:
            with self.subTest(row=row.number, key=row.key):
                self.assertEqual(row.disposition, "watched")
                self.assertRegex(row.review, r"\d{4}-\d{2}-\d{2}")
                self.assertRegex(row.owner, r"@[a-z]")

    def test_calendar_rows_stay_out_of_the_disposition_tally(self):
        # `watched` "is a review obligation, not a scope disposition ...
        # deliberately not one of the four words in the disposition vocabulary".
        # If calendar rows leaked into parse_rows the document's own tally would
        # read 16, and tests/test_scope_ledger.py would have to admit a fifth
        # word -- which would then let a real ledger row be dispositioned
        # `watched` and pass.
        ledger_rows = parse_rows(read_ledger(LEDGER_PATH))
        self.assertEqual(len(ledger_rows), 13)
        self.assertNotIn("watched", {row.disposition for row in ledger_rows})
        calendar_keys = {row.key for row in parse_calendar_rows(read_ledger(LEDGER_PATH))}
        self.assertEqual(calendar_keys & {row.key for row in ledger_rows}, set())

    def test_a_back_dated_calendar_row_fails_and_names_the_row_and_its_reviewer(self):
        # The negative test whose absence made the dates a promise rather than a
        # guard. Twenty months overdue used to exit 0.
        with mutated_ledger(redated_calendar_row(1, "2025-01-01")) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])

        self.assertEqual(code, 1)
        self.assertEqual(len(problems["expired"]), 1, problems["expired"])
        message = problems["expired"][0]
        self.assertIn("2025-01-01", message)
        self.assertIn("m365-consumption-surfaces", message)
        self.assertIn("review calendar row 1", message)
        self.assertIn("@readme", message)
        self.assertIn("m365-consumption-surfaces", output)
        self.assertNotIn("Clean:", output)
        # Nothing else moved: the calendar is only ever held to its dates.
        self.assertEqual(problems["undisposed"], [])
        self.assertEqual(problems["stale"], [])
        self.assertEqual(problems["undeclared"], [])
        self.assertEqual(problems["parse"], [])

    def test_the_calendar_remedy_is_not_the_exclusion_remedy(self):
        # The two failures are discharged differently and must not read alike: an
        # exclusion is re-justified, a calendar row is re-read against its public
        # sources and re-dated with a finding recorded, including a nil finding.
        with mutated_ledger(redated_calendar_row(2, "2025-01-01")) as path:
            calendar = audit(path)["expired"][0]
        with mutated_ledger(("| 2026-12-24 |", "| 2025-01-01 |")) as path:
            exclusion = audit(path)["expired"][0]

        self.assertIn("dataflows", exclusion)
        self.assertIn("re-verify the reason", exclusion)
        self.assertNotIn("review log", exclusion)

        self.assertIn("in-fabric-agent-surfaces", calendar)
        self.assertIn("re-read the public sources", calendar)
        self.assertIn("review log", calendar)
        self.assertIn("nil finding is still a finding", calendar)
        self.assertNotIn("re-verify the reason", calendar)
        # Both keep the no-bulk-re-dating sentence: the cost is the point.
        for message in (calendar, exclusion):
            self.assertIn("no bulk re-dating command", message)

    def test_the_named_reviewer_is_a_handle_not_the_whole_routing_cell(self):
        # The reviewer cell carries the reviewer *and* the routing for a finding.
        # Splicing the whole cell mid-sentence produced "... and to `@semantic`
        # must re-read ...", which reads as gibberish at the moment somebody is
        # being asked to do work.
        with mutated_ledger(redated_calendar_row(3, "2025-01-01")) as path:
            message = audit(path)["expired"][0]
        self.assertIn("-- @readme must re-read the public sources", message)
        # ...and the routing survives, at the end, where a finding needs it.
        self.assertIn("@roadmap-planner", message)

    def test_a_calendar_row_that_loses_its_date_fails(self):
        # On the calendar *every* row must be dated -- the date is the whole
        # mechanism -- where in the ledger only `deliberately excluded` is
        # contractually dated because `open` rows are tracked by a sprint.
        with mutated_ledger(redated_calendar_row(1, "n/a")) as path:
            problems = audit(path)
            code, _output = run(["--ledger", path])
        self.assertEqual(code, 1)
        self.assertEqual(len(problems["expired"]), 1, problems["expired"])
        self.assertIn("watched by nobody", problems["expired"][0])
        self.assertIn("@readme", problems["expired"][0])

    def test_a_calendar_date_still_in_the_future_is_silent(self):
        # Expiry must fire on the date, not on the presence of a date, or the
        # calendar is permanently red and gets switched off.
        future = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()
        with mutated_ledger(redated_calendar_row(1, future)) as path:
            self.assertEqual(count_problems(audit(path)), 0)

    def test_the_calendar_heading_count_is_held_to_the_same_assertion(self):
        with mutated_ledger((CALENDAR_HEADING, CALENDAR_HEADING.replace("3 rows", "2 rows"))) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])
        self.assertEqual(code, 1)
        self.assertTrue(problems["parse"])
        self.assertIn("states 2 rows but 3 parsed", output)
        self.assertIn("review calendar section", output)

    def test_deleting_the_calendar_section_fails_rather_than_unscheduling_it(self):
        # Wiring the dates up and then losing the heading to a rename or a typo
        # would put the obligations back where Sprint 7.3 found them:
        # scheduled-looking and never due. That must cost a deliberate edit to
        # REQUIRED_CALENDAR_SECTIONS, by @tester, not a silent green build.
        with mutated_ledger((CALENDAR_HEADING, "## The review calendar")) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])
        self.assertEqual(code, 1)
        self.assertEqual(len(problems["parse"]), 1, problems["parse"])
        self.assertIn("0 review-calendar section(s) parsed", problems["parse"][0])
        self.assertIn("silently stop coming due", problems["parse"][0])
        self.assertIn("@tester", output)
        self.assertEqual(problems["expired"], [], "the rows are gone, not expired")

    def test_calendar_rows_are_never_reconciled_against_a_constant(self):
        # "They dispose no constant, so undisposed/stale are meaningless for them
        # and would fail on arrival." Proven while the reconciliation is actually
        # firing on something else, so the assertion is not vacuous.
        from fabric_iq.collectors import fabric_api

        shrunk = tuple(k for k in fabric_api.WORKSPACE_ITEM_KEYS if k != "Notebook")
        with source_attribute(fabric_api, "WORKSPACE_ITEM_KEYS", shrunk):
            problems = audit()
        self.assertEqual(len(problems["stale"]), 1, problems["stale"])
        reported = " ".join(problems["stale"] + problems["undisposed"] + problems["sources"])
        for row in parse_calendar_rows(read_ledger(LEDGER_PATH)):
            self.assertNotIn(row.key, reported)

    def test_the_forward_cost_is_every_dated_row_in_both_kinds(self):
        # "Once wired, 2026-12-25 goes red with eight per-row edits instead of
        # five." Asserted as the invariant rather than as the number 8: every row
        # carrying a date comes due, and the calendar rows are among them.
        text = read_ledger(LEDGER_PATH)
        dated = [
            row
            for row in parse_rows(text) + parse_calendar_rows(text)
            if re.search(r"\d{4}-\d{2}-\d{2}", row.review)
        ]
        self.assertGreaterEqual(len(dated), 8)
        expired = audit(LEDGER_PATH, as_of=datetime.date(2027, 1, 1))["expired"]
        self.assertEqual(len(expired), len(dated))
        for row in parse_calendar_rows(text):
            self.assertTrue(
                any(row.key in message for message in expired),
                f"calendar row {row.number} ({row.key}) never comes due",
            )


class TestASectionMustNameADeclaredSource(unittest.TestCase):
    """The hole inside the anti-drift gate, found by @readme and not exploited.

    Renaming a heading to ``## The ledger -- `TOTALLY_FAKE_CONSTANT`, 3 rows``
    parsed cleanly, printed ``Rows parsed: 3 under `TOTALLY_FAKE_CONSTANT``` and
    exited 0. Nothing checked that a parsed section mapped to a *declared*
    source, so "do not invent a constant to satisfy the parser" was enforced by
    an author's integrity rather than by this gate -- the vacuous-gate pattern
    living inside the anti-drift gate, and the same family as the Sprint 5.0.1
    defect where the ownership parser could not read a dotted path and reported
    clean over a file it had never opened.
    """

    FAKE_SECTION = (
        "\n## The ledger \u2014 `TOTALLY_FAKE_CONSTANT`, 1 rows\n\n"
        "| # | Item key | Disposition | Basis | Owner | Review by |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | `Invented` | **open** | Sprint 9 | `@tester` | n/a |\n"
    )

    def test_every_parsed_section_on_the_real_tree_names_a_declared_source(self):
        declared = {source.attribute for source in DECLARED_SOURCES}
        ledgers = [s for s in parse_sections(read_ledger(LEDGER_PATH)) if s.kind == LEDGER_KIND]
        self.assertTrue(ledgers, "non-vacuity: at least one ledger section must parse")
        for section in ledgers:
            self.assertIn(section.source, declared)

    def test_a_section_naming_a_constant_that_does_not_exist_fails_and_is_named(self):
        # Exactly the mutation reproduced on 2026-09-25, which used to exit 0.
        with mutated_ledger(
            (CALENDAR_HEADING, "## The ledger \u2014 `TOTALLY_FAKE_CONSTANT`, 3 rows")
        ) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])

        self.assertEqual(code, 1)
        self.assertEqual(len(problems["undeclared"]), 1, problems["undeclared"])
        message = problems["undeclared"][0]
        self.assertIn("TOTALLY_FAKE_CONSTANT", message)
        self.assertIn("not declared in DECLARED_SOURCES", message)
        self.assertIn("@tester", message)
        self.assertIn("TOTALLY_FAKE_CONSTANT", output)
        self.assertNotIn("Clean:", output)
        # The same mutation also destroyed the calendar, and that is reported
        # too: two distinct things went wrong and the gate says both.
        self.assertTrue(problems["parse"])

    def test_a_fake_section_added_beside_the_real_ones_fails_on_its_own(self):
        # Isolates the new check: the real ledger and the real calendar are both
        # intact, so `undeclared` is the only thing that can fire.
        text = read_ledger(LEDGER_PATH) + self.FAKE_SECTION
        with ledger_copy(text) as path:
            problems = audit(path)
            code, output = run(["--ledger", path])
        self.assertEqual(code, 1)
        self.assertEqual(count_problems(problems), 1, problems)
        self.assertIn("TOTALLY_FAKE_CONSTANT", problems["undeclared"][0])
        self.assertIn("Ledger sections naming a source this gate does not declare", output)

    def test_a_real_but_undeclared_constant_fails_too(self):
        # The quieter shape: a section for a constant that genuinely exists but
        # was never added to DECLARED_SOURCES. Its rows parse, count, expire and
        # print while nothing reconciles them against code -- a section that
        # looks gated and is not.
        text = read_ledger(LEDGER_PATH) + self.FAKE_SECTION.replace(
            "TOTALLY_FAKE_CONSTANT", "TENANT_SETTING_MAP"
        )
        with ledger_copy(text) as path:
            problems = audit(path)
        self.assertEqual(len(problems["undeclared"]), 1, problems)
        self.assertIn("TENANT_SETTING_MAP", problems["undeclared"][0])

    def test_the_mapping_is_a_bijection_in_both_directions(self):
        # Renaming the one real section fires both halves at once: the declared
        # source has no section (check 2, which already existed) and the section
        # names nothing declared (check 6, added here).
        with mutated_ledger(
            (
                "## The ledger \u2014 `WORKSPACE_ITEM_KEYS`, 13 rows",
                "## The ledger \u2014 `RENAMED_KEYS`, 13 rows",
            )
        ) as path:
            problems = audit(path)
        self.assertTrue(problems["sources"], "declared source with no section must fail")
        self.assertIn("has no '## The ledger", problems["sources"][0])
        self.assertTrue(problems["undeclared"], "section naming nothing declared must fail")
        self.assertIn("RENAMED_KEYS", problems["undeclared"][0])

    def test_the_calendar_is_exempt_by_construction_not_by_exception(self):
        # The calendar heading names a class, never an identifier, so it cannot
        # reach the declared-source check at all -- which is why writing these
        # rows needed no fake constant in the first place.
        calendars = [s for s in parse_sections(read_ledger(LEDGER_PATH)) if s.kind == CALENDAR_KIND]
        self.assertTrue(calendars)
        for section in calendars:
            self.assertNotRegex(section.source, r"^[A-Z_][A-Z0-9_]*$")
        self.assertEqual(audit()["undeclared"], [])


class TestTheGateHasNoEscapeHatch(unittest.TestCase):
    """Design rules that are only real if something enforces them."""

    def test_there_is_no_bulk_update_or_accept_all_flag(self):
        # "The cost is manual work on every fire, and that cost is the point."
        with open(SCRIPT, encoding="utf-8") as handle:
            script = handle.read()
        for flag in ("--update", "--accept-all", "--fix", "--regenerate", "--ignore"):
            self.assertNotIn(f'"{flag}"', script, f"{flag} must not exist")
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stderr(io.StringIO()):
                main(["--update"])
        self.assertEqual(raised.exception.code, 2)

    def test_the_gate_never_reads_the_network(self):
        # "A CI gate that fetches a vendor page is non-deterministic, breaks the
        # standard-library-only contract, and fails in the place people trust
        # most." Whether a documented product fact still holds is what the
        # review-by date is for -- a human obligation, not a fetch.
        for module in imported_modules():
            root = module.split(".")[0]
            self.assertNotIn(
                root,
                {"urllib", "http", "socket", "ssl", "ftplib", "requests", "webbrowser", "smtplib"},
                f"the gate imports {module}; it must never read the network",
            )
        with open(SCRIPT, encoding="utf-8") as handle:
            self.assertNotIn("urlopen", handle.read())

    def test_the_gate_depends_on_nothing_outside_the_standard_library(self):
        imports = {module.split(".")[0] for module in imported_modules()}
        allowed = {
            "argparse", "datetime", "importlib", "os", "re", "sys", "typing",
            "__future__", "fabric_iq",
        }
        self.assertEqual(imports - allowed, set())


class TestTheRealLedgerIsNeverMutated(unittest.TestCase):
    """docs/SCOPE_LEDGER.md is @readme's; this suite only ever reads it."""

    def test_the_real_ledger_is_byte_identical_after_every_mutation_proof(self):
        with open(LEDGER_PATH, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        with mutated_ledger(("| 2026-12-24 |", "| 2020-01-01 |")) as path:
            self.assertNotEqual(path, LEDGER_PATH)
            run(["--ledger", path])
        with open(LEDGER_PATH, "rb") as handle:
            self.assertEqual(hashlib.sha256(handle.read()).hexdigest(), digest)


class TestScopeLedgerGateOwnership(unittest.TestCase):
    """An unowned gate degrades into a check that fails open in silence."""

    MODULE = "scripts/check_scope_ledger.py"

    def test_the_gate_is_inside_the_audited_universe(self):
        from scripts.check_agent_ownership import audited_modules

        self.assertIn(self.MODULE, audited_modules())

    def test_the_gate_is_claimed_exactly_once_by_tester(self):
        from scripts.check_agent_ownership import claims

        self.assertEqual(claims().get(self.MODULE), ["tester"])

    def test_dropping_the_claim_fails_the_module_audit(self):
        # The ownership gate catches "required but not claimed" and never
        # "claimed but not required", so the claim and the module have to land
        # together and the failing direction is the module existing unclaimed.
        from scripts.check_agent_ownership import audit as audit_ownership

        agents_dir = os.path.join(REPO_ROOT, ".github", "agents")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            agents = os.path.join(tmp, "agents")
            shutil.copytree(agents_dir, agents)
            path = os.path.join(agents, "tester.agent.md")
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn(f"`{self.MODULE}`", text, "the claim must exist before removal")
            self.assertEqual(audit_ownership(agents, REPO_ROOT), ([], {}))

            kept = [line for line in text.splitlines(True) if f"`{self.MODULE}`" not in line]
            with open(path, "w", encoding="utf-8") as handle:
                handle.writelines(kept)

            unclaimed, duplicated = audit_ownership(agents, REPO_ROOT)
            self.assertEqual(unclaimed, [self.MODULE])
            self.assertEqual(duplicated, {})


class TestTheGateRunsInCI(unittest.TestCase):
    """"The check runs in CI as its own named step" -- Sprint 7.2 release gate."""

    def test_ci_runs_the_scope_ledger_check_as_its_own_named_step(self):
        path = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml")
        with open(path, encoding="utf-8") as handle:
            workflow = handle.read()
        self.assertIn("python scripts/check_scope_ledger.py", workflow)
        step = re.search(
            r"- name: ([^\n]*[Ss]cope ledger[^\n]*)\n\s+run: python scripts/check_scope_ledger\.py",
            workflow,
        )
        self.assertIsNotNone(step, "the check must be its own named CI step")

    def test_it_sits_with_the_other_gates_and_before_the_end_to_end_run(self):
        path = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml")
        with open(path, encoding="utf-8") as handle:
            workflow = handle.read()
        order = [
            workflow.index("python scripts/check_agent_ownership.py"),
            workflow.index("python scripts/check_evidence_sinks.py"),
            workflow.index("python scripts/check_scope_ledger.py"),
            workflow.index("python assess.py --inventory examples/sample_tenant --review"),
        ]
        self.assertEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main()
