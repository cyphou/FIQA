"""Multi-agent environment integrity.

The agent files are executable documentation: they route work and declare
ownership. Drift here is silent until someone edits a module nobody owns.
"""

import os
import re
import tempfile
import unittest

from tests.helpers import REPO_ROOT

AGENTS_DIR = os.path.join(REPO_ROOT, ".github", "agents")

EXPECTED_AGENTS = {
    "orchestrator", "collector", "scorer", "tenant", "semantic", "dataagent",
    "preceptor", "remediation", "lakehouse", "tester", "readme",
    "roadmap-planner", "security",
}


def agent_files():
    return {
        f[: -len(".agent.md")]: os.path.join(AGENTS_DIR, f)
        for f in os.listdir(AGENTS_DIR)
        if f.endswith(".agent.md")
    }


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestAgentRoster(unittest.TestCase):
    def test_every_expected_agent_exists(self):
        self.assertEqual(set(agent_files()), EXPECTED_AGENTS)

    def test_shared_instructions_exist(self):
        self.assertTrue(os.path.exists(os.path.join(AGENTS_DIR, "shared.instructions.md")))

    def test_copilot_instructions_exist(self):
        self.assertTrue(
            os.path.exists(os.path.join(REPO_ROOT, ".github", "copilot-instructions.md"))
        )

    def test_every_agent_declares_front_matter(self):
        for agent, path in agent_files().items():
            with self.subTest(agent=agent):
                text = read(path)
                self.assertTrue(text.startswith("---\n"), "missing YAML front matter")
                front = text.split("---", 2)[1]
                self.assertIn("name:", front)
                self.assertIn("description:", front)
                self.assertIn("tools:", front)

    def test_every_agent_declares_constraints(self):
        for agent, path in agent_files().items():
            with self.subTest(agent=agent):
                self.assertIn("## Constraints", read(path))

    def test_shared_rules_state_the_core_invariants(self):
        text = read(os.path.join(AGENTS_DIR, "shared.instructions.md"))
        for claim in ("NOT_EVALUATED", "39", "read-only", "Preceptorship"):
            with self.subTest(claim=claim):
                self.assertIn(claim, text)

    def test_roster_table_lists_every_agent(self):
        text = read(os.path.join(AGENTS_DIR, "shared.instructions.md"))
        for agent in EXPECTED_AGENTS:
            with self.subTest(agent=agent):
                self.assertIn(f"`@{agent}`", text)


class TestOwnership(unittest.TestCase):
    def test_every_module_is_claimed_exactly_once(self):
        from scripts.check_agent_ownership import audit

        unclaimed, duplicated = audit()
        self.assertEqual(unclaimed, [], f"modules with no owner: {unclaimed}")
        self.assertEqual(duplicated, {}, f"modules with several owners: {duplicated}")

    def test_preceptor_owns_the_review_loop(self):
        from scripts.check_agent_ownership import claims

        self.assertEqual(claims().get("fabric_iq/preceptor.py"), ["preceptor"])

    def test_security_agent_owns_no_module(self):
        from scripts.check_agent_ownership import claims

        owned = [m for m, agents in claims().items() if "security" in agents]
        self.assertEqual(owned, [], "the security agent must stay read-only")

    def test_a_mention_outside_the_claim_block_is_not_a_claim(self):
        # An agent that describes the ownership rule ("every `fabric_iq/` module is
        # claimed exactly once") must not thereby claim every module.
        from scripts.check_agent_ownership import claims

        for module, agents in claims().items():
            with self.subTest(module=module):
                self.assertLessEqual(len(agents), 1, f"{module}: {agents}")


class TestDocumentationOwnership(unittest.TestCase):
    """Release gate criterion 10.

    A document that tells a customer what is collected, who is named in it, and
    how long it is kept is a promise. A promise with no accountable agent goes
    stale without anyone noticing, which is how a privacy claim becomes false.
    """

    def test_every_required_document_exists(self):
        from scripts.check_agent_ownership import REQUIRED_DOCS

        for doc in REQUIRED_DOCS:
            with self.subTest(doc=doc):
                self.assertTrue(
                    os.path.exists(os.path.join(REPO_ROOT, doc.replace("/", os.sep))),
                    f"{doc} is required to be owned but does not exist",
                )

    def test_security_is_never_the_accountable_owner(self):
        from scripts.check_agent_ownership import REQUIRED_DOCS

        self.assertNotIn("security", set(REQUIRED_DOCS.values()))

    def test_every_required_document_is_claimed_by_exactly_one_agent(self):
        from scripts.check_agent_ownership import REQUIRED_DOCS, audit_docs

        unclaimed, duplicated, misassigned = audit_docs()
        expected = {doc: f"@{REQUIRED_DOCS[doc]}" for doc in unclaimed}
        self.assertEqual(unclaimed, [], f"documentation with no owner: {expected}")
        self.assertEqual(duplicated, {}, f"documentation with several owners: {duplicated}")
        self.assertEqual(
            misassigned, {}, f"documentation claimed by the wrong agent: {misassigned}"
        )


class TestOwnershipCheckerBehaviour(unittest.TestCase):
    """The checker itself, against synthetic agent files in a temp tree."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        self.agents = os.path.join(self.root, ".github", "agents")
        os.makedirs(self.agents)
        os.makedirs(os.path.join(self.root, "fabric_iq"))
        with open(os.path.join(self.root, "fabric_iq", "scoring.py"), "w", encoding="utf-8") as h:
            h.write("# synthetic module\n")
        self.required = {"docs/PRIVACY.md": "readme", "fabric/README.md": "orchestrator"}

    def write_agent(self, name, claim_lines, extra=""):
        body = (
            "---\nname: x\ndescription: x\ntools: []\n---\n\n"
            "## Your Files (You Own These)\n\n"
            + "\n".join(claim_lines)
            + "\n\n## Notes\n\n"
            + extra
            + "\n\n## Constraints\n\n- none\n"
        )
        with open(os.path.join(self.agents, f"{name}.agent.md"), "w", encoding="utf-8") as handle:
            handle.write(body)

    def audit_docs(self):
        from scripts.check_agent_ownership import audit_docs

        return audit_docs(self.agents, self.root, self.required)

    def test_a_claimed_document_is_clean(self):
        self.write_agent("readme", ["- `docs/PRIVACY.md` — retention claim"])
        self.write_agent("orchestrator", ["- `fabric/README.md` — deployment surface"])

        self.assertEqual(self.audit_docs(), ([], {}, {}))

    def test_an_unclaimed_document_fails(self):
        self.write_agent("readme", ["- `docs/PRIVACY.md` — retention claim"])
        self.write_agent("orchestrator", ["- `assess.py` — CLI"])

        unclaimed, duplicated, misassigned = self.audit_docs()

        self.assertEqual(unclaimed, ["fabric/README.md"])
        self.assertEqual((duplicated, misassigned), ({}, {}))

    def test_a_doubly_claimed_document_fails(self):
        self.write_agent("readme", ["- `docs/PRIVACY.md` — retention claim"])
        self.write_agent(
            "orchestrator",
            ["- `docs/PRIVACY.md` — also mine", "- `fabric/README.md` — deployment surface"],
        )

        _unclaimed, duplicated, _misassigned = self.audit_docs()

        self.assertEqual(duplicated, {"docs/PRIVACY.md": ["orchestrator", "readme"]})

    def test_a_document_claimed_by_the_wrong_agent_fails(self):
        self.write_agent("preceptor", ["- `docs/PRIVACY.md` — retention claim"])
        self.write_agent("orchestrator", ["- `fabric/README.md` — deployment surface"])

        _unclaimed, _duplicated, misassigned = self.audit_docs()

        self.assertEqual(misassigned, {"docs/PRIVACY.md": ["preceptor"]})

    def test_a_directory_claim_covers_the_documents_inside_it(self):
        self.write_agent("readme", ["- `docs/` — all documentation"])
        self.write_agent("orchestrator", ["- `fabric/` — Fabric item definitions"])

        self.assertEqual(self.audit_docs(), ([], {}, {}))

    def test_a_pointer_to_another_owner_is_not_a_claim(self):
        self.write_agent(
            "readme",
            [
                "- `docs/PRIVACY.md` — retention claim",
                "- `fabric/README.md` is owned by **@orchestrator**",
            ],
        )

        unclaimed, _duplicated, _misassigned = self.audit_docs()

        self.assertEqual(unclaimed, ["fabric/README.md"])

    def test_a_mention_after_the_claim_block_is_not_a_claim(self):
        self.write_agent("readme", ["- `docs/PRIVACY.md` — retention claim"])
        self.write_agent(
            "orchestrator",
            ["- `assess.py` — CLI"],
            extra="Coordinate with the owner of `fabric/README.md` before editing it.",
        )

        unclaimed, _duplicated, _misassigned = self.audit_docs()

        self.assertEqual(unclaimed, ["fabric/README.md"])

    def test_prose_in_backticks_is_not_read_as_a_path(self):
        from scripts.check_agent_ownership import claims

        self.write_agent(
            "readme",
            [
                "- `docs/PRIVACY.md` — retention claim",
                "- `fabric/README.md` — deployment surface",
                "- `NOT_EVALUATED` and `run_id` are contracts, not files",
            ],
        )

        claimed = claims(self.agents, self.root, self.required)

        self.assertNotIn("NOT_EVALUATED", claimed)
        self.assertNotIn("run_id", claimed)

    def test_the_module_audit_still_reports_an_unclaimed_module(self):
        from scripts.check_agent_ownership import audit

        self.write_agent("readme", ["- `docs/PRIVACY.md` — retention claim"])

        unclaimed, duplicated = audit(self.agents, self.root)

        self.assertEqual(unclaimed, ["fabric_iq/scoring.py"])
        self.assertEqual(duplicated, {})



class TestRoadmap(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(REPO_ROOT, "docs", "ROADMAP.md")

    def test_roadmap_exists(self):
        self.assertTrue(os.path.exists(self.path))

    def test_every_phase_declares_an_exit_gate(self):
        text = read(self.path)
        phases = re.findall(r"^## Phase \d+.*$", text, flags=re.MULTILINE)
        self.assertGreaterEqual(len(phases), 5)
        sections = re.split(r"^## (?=Phase \d+)", text, flags=re.MULTILINE)[1:]
        for section in sections:
            title = section.splitlines()[0]
            with self.subTest(phase=title):
                self.assertIn("Exit gate", section, f"phase without an exit gate: {title}")


if __name__ == "__main__":
    unittest.main()
