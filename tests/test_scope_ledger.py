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
   fourteenth key added tomorrow appears here as a row. That is the drift detector
   Sprint 7.2 delivers, and the ledger says so in its own words ("it is not a
   detector ... `WORKSPACE_ITEM_KEYS` can gain a fourteenth key tomorrow and this
   document will not notice"). Asserting it here would design 7.2 by accident and
   falsify a sentence in a document this agent does not own. It was verified by
   hand at this revision -- the 13 rows are a bijection with the 13 keys -- and the
   standing check belongs to 7.2.

What is left is the rot this document can suffer *on its own*: a row that gains a
second disposition, an exclusion whose review-by date is dropped, an untriaged row
that loses the name of the agent who owes the answer, a tally that stops matching
the table, or an `assessed` row whose cited rule range drifts away from the
registry. Those are real, they are silent, and they are green today.
"""

import os
import re
import unittest

from tests.helpers import REPO_ROOT

LEDGER = os.path.join(REPO_ROOT, "docs", "SCOPE_LEDGER.md")

#: `| 6 | `dataflows` | **deliberately excluded** | reason | `@readme` | 2026-12-24 |`
_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*\*\*([a-z ]+)\*\*\s*\|"
    r"(.*?)\|(.*?)\|(.*?)\|\s*$"
)
_RULE_ID = re.compile(r"\b([A-Z]{3}-\d{3})\b")
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_AGENT = re.compile(r"@([a-z][a-z-]*)")


def _read():
    with open(LEDGER, encoding="utf-8") as handle:
        return handle.read()


def _rows(text=None):
    """Parse the ledger table into ``[(n, key, disposition, basis, owner, review)]``."""
    parsed = []
    for line in (text if text is not None else _read()).splitlines():
        match = _ROW.match(line)
        if match:
            number, key, disposition, basis, owner, review = match.groups()
            parsed.append(
                (int(number), key, disposition.strip(), basis.strip(), owner.strip(), review.strip())
            )
    return parsed


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
