"""Internal consistency of `docs/SCOPE_LEDGER.md` (Sprint 7.1).

The ledger's value is that a reader can tell a *decision* from an *oversight*.
Every assertion below holds the document to a contract the document writes for
itself -- the "Must carry" column of its own disposition vocabulary, and its own
sentence "Every key resolves to exactly one disposition; none carries two". None
of it is a contract this suite invented, and none of it obliges @readme to write
a judgement that belongs to another agent.

**What is deliberately NOT asserted here, and why.**

1. *That the `untriaged` disposition is empty.* That is the Phase 7 release gate,
   and four rows carry it today by design: @readme routed the underlying question
   to @dataagent rather than manufacturing a reason, and "excluded, no reason" is
   worse than silence because it looks decided. A test encoding the release gate
   would be red on arrival and would pressure someone into inventing the very
   placeholder the ledger exists to prevent. Every check below is stated as a
   *conditional* over the rows that carry a disposition, so it is vacuously true
   when a bucket empties: triaging the four rows must never turn this file red.

2. *Reconciliation against the live `WORKSPACE_ITEM_KEYS` constant* -- that a
   fourteenth key added tomorrow appears here as a row. **Delivered in Sprint
   7.2**, by `scripts/check_scope_ledger.py` and `tests/test_scope_ledger_gate.py`,
   which is where the bijection assertion now lives along with the negative tests
   that prove the gate can fail. It stays out of *this* file because the two ask
   different questions: this file asks whether the document is internally honest,
   that one asks whether the document still matches the code. Both read the table
   through the same parser -- `parse_rows` in the gate script -- because two
   parsers for one table is its own drift hazard, and the second one to go stale
   would be the one nobody ran.

What is left is the rot this document can suffer *on its own*: a row that gains a
second disposition, an exclusion whose review-by date is dropped, an untriaged row
that loses the name of the agent who owes the answer, a tally that stops matching
the table, or an `assessed` row whose cited rule range drifts away from the
registry. Those are real, they are silent, and they are green today.
"""

import os
import re
import unittest

from scripts.check_scope_ledger import ISO_DATE as _ISO_DATE
from scripts.check_scope_ledger import (
    LEDGER_PATH,
    parse_calendar_rows,
    parse_rows,
    read_ledger,
)
from tests.helpers import REPO_ROOT

LEDGER = LEDGER_PATH

_RULE_ID = re.compile(r"\b([A-Z]{3}-\d{3})\b")
_AGENT = re.compile(r"@([a-z][a-z-]*)")


def _read():
    return read_ledger(LEDGER)


def _rows(text=None):
    """Parse the ledger table into ``[(n, key, disposition, basis, owner, review)]``.

    Delegates to the gate script's parser rather than keeping a second copy. When
    Sprint 7.2 made the ledger executable the table gained a *second* reader, and
    two regexes over one table drift apart silently -- in the direction where the
    less-exercised one starts matching nothing and its assertions pass over an
    empty set.
    """
    return parse_rows(text if text is not None else _read())


def _calendar_rows(text=None):
    """The review-calendar rows, which are deliberately *not* dispositions.

    Kept apart from :func:`_rows` because the document keeps them apart: folding
    them in would make the stated tally read 16 instead of 13 and would force the
    vocabulary assertion to admit a fifth word, which would in turn let a real
    ledger row be dispositioned ``watched`` and still pass.
    """
    return parse_calendar_rows(text if text is not None else _read())


class TestScopeLedgerParses(unittest.TestCase):
    def test_the_ledger_exists_and_its_table_is_parseable(self):
        # Non-vacuity guard for every test below: if the table stops matching the
        # row shape, each "for every row" assertion would pass over nothing and
        # this file would silently stop checking the document.
        self.assertTrue(os.path.exists(LEDGER), f"{LEDGER} is a REQUIRED_DOCS entry")
        self.assertTrue(_rows(), "no ledger row parsed -- the table shape changed")

    def test_the_row_count_matches_the_count_the_document_states(self):
        rows = _rows()
        heading = f"## The ledger — `WORKSPACE_ITEM_KEYS`, {len(rows)} rows"
        self.assertIn(
            heading,
            _read(),
            f"{len(rows)} rows parsed, but the heading states a different count",
        )


class TestOneDispositionPerKey(unittest.TestCase):
    """"Every key resolves to exactly one disposition; none carries two." """

    def test_no_item_key_appears_twice(self):
        keys = [key for _, key, *_ in _rows()]
        duplicated = sorted({key for key in keys if keys.count(key) > 1})
        self.assertEqual(duplicated, [], f"item keys carrying two dispositions: {duplicated}")

    def test_every_disposition_is_one_the_vocabulary_defines(self):
        text = _read()
        vocabulary = {
            "assessed", "deliberately excluded", "open", "untriaged",
        }
        for word in vocabulary:
            self.assertIn(
                f"**{word}**", text, f"the vocabulary table no longer defines {word!r}"
            )
        for number, key, disposition, *_ in _rows(text):
            with self.subTest(row=number, key=key):
                self.assertIn(
                    disposition,
                    vocabulary,
                    f"row {number} ({key}) uses a disposition the vocabulary does not define",
                )

    def test_the_tally_matches_the_table(self):
        counted = {}
        for _, _, disposition, *_ in _rows():
            counted[disposition] = counted.get(disposition, 0) + 1
        stated = f"**Tally: {counted.get('assessed', 0)} assessed, {counted.get('open', 0)} open, " \
                 f"{counted.get('deliberately excluded', 0)} deliberately excluded, " \
                 f"{counted.get('untriaged', 0)} untriaged.**"
        self.assertIn(
            stated,
            _read(),
            f"the table counts {counted}, which the stated tally no longer reports",
        )


class TestTheReviewCalendarIsInternallyHonest(unittest.TestCase):
    """The calendar's own claims about itself (Sprint 7.3).

    `watched` rows are *not* dispositions -- the document says so in its own
    prose -- so they are parsed separately, kept out of the tally, and held to a
    different contract: a reviewer, a date, public sources, and a finding written
    down. Whether those dates are *enforced* is a gate question and lives in
    `tests/test_scope_ledger_gate.py`; whether the table is honest about itself is
    this file's question.

    What is deliberately NOT asserted here: that a review found what it says it
    found. "It guarantees that somebody looked on a stated date. It never
    guarantees that they saw" -- and no test can close that gap, so none pretends
    to.
    """

    def test_the_calendar_parses_and_states_its_own_row_count(self):
        rows = _calendar_rows()
        self.assertTrue(rows, "no calendar row parsed -- the table shape changed")
        heading = f"## The review calendar — classes that exist only as prose, {len(rows)} rows"
        self.assertIn(heading, _read(), "the heading states a count the table does not match")

    def test_watched_is_deliberately_not_a_disposition_word(self):
        # "`watched` is a review obligation, not a scope disposition. It is
        # deliberately not one of the four words in the disposition vocabulary."
        # If it ever became one, a real ledger row could be dispositioned
        # `watched` -- disposed of by a calendar entry that reconciles nothing.
        self.assertNotIn("| **watched** | ", _read().split("## The ledger")[0])
        self.assertNotIn("watched", {disposition for _, _, disposition, *_ in _rows()})
        for number, key, disposition, *_ in _calendar_rows():
            with self.subTest(row=number, key=key):
                self.assertEqual(disposition, "watched")

    def test_every_watched_row_names_a_reviewer_a_date_and_public_sources(self):
        for number, key, _disposition, basis, owner, review in _calendar_rows():
            with self.subTest(row=number, key=key):
                self.assertRegex(
                    review, _ISO_DATE, f"calendar row {number} ({key}) carries no review-by date"
                )
                self.assertRegex(
                    owner, _AGENT, f"calendar row {number} ({key}) names nobody to review it"
                )
                self.assertIn(
                    "https://",
                    basis,
                    f"calendar row {number} ({key}) cites no public source to re-read -- "
                    "a review obligation with no named source cannot be discharged",
                )
                self.assertIn(
                    "Found:",
                    basis,
                    f"calendar row {number} ({key}) records no finding from its last review",
                )

    def test_every_watched_class_appears_in_the_review_log(self):
        # "A nil result is the normal outcome of a quarterly read and it must be
        # written down with its date and the sources consulted, otherwise the next
        # reviewer cannot distinguish a checked surface from an unchecked one."
        text = _read()
        for number, key, *_ in _calendar_rows():
            with self.subTest(row=number, key=key):
                self.assertRegex(
                    text,
                    re.compile(rf"^\|\s*\d{{4}}-\d{{2}}-\d{{2}}\s*\|\s*`{re.escape(key)}`\s*\|", re.M),
                    f"`{key}` is watched but no dated review-log row records a reading of it",
                )


class TestEveryRowCarriesWhatItsDispositionRequires(unittest.TestCase):

    """The "Must carry" column of the ledger's own disposition vocabulary.

    Each test is a conditional over the rows that carry one disposition, so it
    stays green when that bucket empties. Triaging the four `untriaged` rows --
    the outcome Sprint 7.1 wants -- must not break this suite.
    """

    def test_every_deliberately_excluded_row_carries_a_review_by_date(self):
        # An exclusion with no review-by date never comes back for review; it
        # becomes permanent by neglect rather than by decision.
        for number, key, disposition, _basis, _owner, review in _rows():
            if disposition != "deliberately excluded":
                continue
            with self.subTest(row=number, key=key):
                self.assertRegex(
                    review,
                    _ISO_DATE,
                    f"row {number} ({key}) is excluded but carries no yyyy-mm-dd review-by date",
                )

    def test_every_deliberately_excluded_row_carries_a_reason_and_an_owner(self):
        for number, key, disposition, basis, owner, _review in _rows():
            if disposition != "deliberately excluded":
                continue
            with self.subTest(row=number, key=key):
                # "An exclusion reading 'out of scope' with no reason is worse than
                # silence, because it looks decided."
                self.assertGreater(
                    len(basis), 40, f"row {number} ({key}) is excluded with no stated reason"
                )
                self.assertRegex(
                    owner, _AGENT, f"row {number} ({key}) is excluded but names no owning agent"
                )

    def test_every_untriaged_row_names_the_agent_who_owes_the_answer(self):
        # This is what makes an honest empty a finding instead of a shrug. It is
        # vacuously true once the rows are triaged, which is the point.
        for number, key, disposition, _basis, owner, _review in _rows():
            if disposition != "untriaged":
                continue
            with self.subTest(row=number, key=key):
                self.assertRegex(
                    owner,
                    _AGENT,
                    f"row {number} ({key}) is untriaged and names nobody to answer it",
                )

    def test_every_open_row_names_the_sprint_that_would_close_it(self):
        for number, key, disposition, basis, _owner, _review in _rows():
            if disposition != "open":
                continue
            with self.subTest(row=number, key=key):
                self.assertRegex(
                    basis,
                    re.compile(r"Sprint\s+\d", re.IGNORECASE),
                    f"row {number} ({key}) is open but names no sprint that would close it",
                )


class TestAssessedRowsMatchTheLiveRegistry(unittest.TestCase):
    """An `assessed` row must carry the rule IDs, and they must still be true.

    This is the one axis where the ledger can be falsified by a change nobody
    made to the ledger: adding REP-012 leaves row 1 reading "11 rules", which is
    a stale row presented as a signed disposition.
    """

    def test_every_assessed_row_cites_a_rule_range_that_matches_the_registry(self):
        from fabric_iq.models import ObjectType
        from fabric_iq.rules import registry

        assessed = [row for row in _rows() if row[2] == "assessed"]
        self.assertTrue(assessed, "no assessed row parsed")

        for number, key, _disposition, basis, _owner, _review in assessed:
            with self.subTest(row=number, key=key):
                named = re.search(r"ObjectType\.([A-Z_]+)", basis)
                self.assertIsNotNone(
                    named, f"row {number} ({key}) cites no ObjectType"
                )
                object_type = getattr(ObjectType, named.group(1), None)
                self.assertIsNotNone(
                    object_type, f"row {number} cites ObjectType.{named.group(1)}, which is gone"
                )

                live = sorted(rule.id for rule in registry.for_type(object_type))
                self.assertTrue(live, f"ObjectType.{named.group(1)} now carries no rule")

                stated = re.search(r"\((\d+)\s+rules", basis)
                self.assertIsNotNone(stated, f"row {number} ({key}) states no rule count")
                self.assertEqual(
                    int(stated.group(1)),
                    len(live),
                    f"row {number} ({key}) states {stated.group(1)} rules, "
                    f"registry holds {len(live)} for ObjectType.{named.group(1)}",
                )

                cited = _RULE_ID.findall(basis)
                self.assertEqual(
                    [cited[0], cited[-1]],
                    [live[0], live[-1]],
                    f"row {number} ({key}) cites the range {cited[0]}-{cited[-1]}, "
                    f"registry spans {live[0]}-{live[-1]}",
                )
                for rule_id in cited:
                    self.assertIn(
                        rule_id, live, f"row {number} cites {rule_id}, which no longer exists"
                    )


class TestScopeLedgerOwnership(unittest.TestCase):
    """The ledger is a collection-capability claim, so it must carry an owner."""

    def test_required_docs_names_readme_as_the_accountable_owner(self):
        from scripts.check_agent_ownership import REQUIRED_DOCS

        self.assertEqual(REQUIRED_DOCS.get("docs/SCOPE_LEDGER.md"), "readme")

    def test_readme_has_claimed_the_scope_ledger(self):
        from scripts.check_agent_ownership import claims

        self.assertEqual(
            claims().get("docs/SCOPE_LEDGER.md"),
            ["readme"],
            "docs/SCOPE_LEDGER.md must be claimed exactly once, by @readme, in the "
            "'Your Files (You Own These)' block of .github/agents/readme.agent.md",
        )

    def test_dropping_the_readme_claim_fails_the_document_audit(self):
        # Non-vacuity proof against the real agent tree: without the claim line the
        # audit must name the ledger and its accountable owner, otherwise the
        # REQUIRED_DOCS entry enforces nothing. A required document left unclaimed
        # for even one commit is the gate-failing-open case Sprint 5.0.1 found.
        import shutil
        import tempfile

        from scripts.check_agent_ownership import REQUIRED_DOCS, audit_docs

        doc = "docs/SCOPE_LEDGER.md"
        agents_dir = os.path.join(REPO_ROOT, ".github", "agents")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            agents = os.path.join(tmp, "agents")
            shutil.copytree(agents_dir, agents)
            path = os.path.join(agents, "readme.agent.md")
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn(f"`{doc}`", text, "the claim must exist before it is removed")

            self.assertEqual(audit_docs(agents, REPO_ROOT), ([], {}, {}))

            kept = [line for line in text.splitlines(True) if f"`{doc}`" not in line]
            with open(path, "w", encoding="utf-8") as handle:
                handle.writelines(kept)

            unclaimed, duplicated, misassigned = audit_docs(agents, REPO_ROOT)

            self.assertEqual(unclaimed, [doc])
            self.assertEqual((duplicated, misassigned), ({}, {}))
            self.assertEqual(REQUIRED_DOCS[doc], "readme")


if __name__ == "__main__":
    unittest.main()
