"""Multi-agent environment integrity.

The agent files are executable documentation: they route work and declare
ownership. Drift here is silent until someone edits a module nobody owns.
"""

import os
import re
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
