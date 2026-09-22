"""Documentation must not drift from the code.

The @readme documentation gate exists because a stale count or an unreproducible
claim in a readiness tool undermines the one thing it sells: trustworthiness.
These tests make the gate executable.
"""

import os
import re
import unittest

from fabric_iq import RULESET_VERSION
from fabric_iq.models import ObjectType, Severity
from fabric_iq.rules import registry
from tests.helpers import REPO_ROOT

DOCS = os.path.join(REPO_ROOT, "docs")

OBJECT_LABEL = {
    ObjectType.TENANT: "Tenant",
    ObjectType.WORKSPACE: "Workspace",
    ObjectType.SEMANTIC_MODEL: "Semantic model",
    ObjectType.REPORT: "Report",
    ObjectType.DATA_AGENT: "Data Agent",
}


def read(*parts):
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class TestRequiredDocuments(unittest.TestCase):
    def test_every_documented_file_exists(self):
        for relative in (
            "README.md", "CHANGELOG.md", "pyproject.toml", ".gitignore", ".env.example",
            "docs/ROADMAP.md", "docs/SCORING.md", "docs/ARCHITECTURE.md",
            "docs/AGENTS.md", "docs/RULES.md", "docs/KNOWN_LIMITATIONS.md",
            ".github/copilot-instructions.md", ".github/workflows/ci.yml",
            ".github/skills/fabric-iq-readiness/SKILL.md",
        ):
            with self.subTest(path=relative):
                self.assertTrue(os.path.exists(os.path.join(REPO_ROOT, *relative.split("/"))))

    def test_readme_internal_links_resolve(self):
        readme = read("README.md")
        for target in re.findall(r"\]\(\./([^)#]+)\)", readme):
            with self.subTest(target=target):
                self.assertTrue(
                    os.path.exists(os.path.join(REPO_ROOT, *target.split("/"))),
                    f"README links to a missing path: {target}",
                )


class TestClaimAccuracy(unittest.TestCase):
    def test_readme_rule_total_matches_the_registry(self):
        self.assertIn(f"{len(registry)} rules", read("README.md"))

    def test_readme_ruleset_version_matches_the_code(self):
        self.assertIn(RULESET_VERSION, read("README.md"))

    def test_readme_per_object_counts_match_the_registry(self):
        readme = read("README.md")
        for object_type, label in OBJECT_LABEL.items():
            rules = registry.for_type(object_type)
            blocking = sum(1 for r in rules if r.severity is Severity.BLOCKING)
            row = re.search(rf"^\| {re.escape(label)} \| (\d+) \| (\d+) \|", readme, re.MULTILINE)
            with self.subTest(object_type=label):
                self.assertIsNotNone(row, f"README has no catalogue row for {label}")
                self.assertEqual(int(row.group(1)), len(rules))
                self.assertEqual(int(row.group(2)), blocking)

    def test_generated_rules_doc_is_current(self):
        from scripts.build_rules_doc import render

        self.assertEqual(read("docs", "RULES.md"), render(),
                         "docs/RULES.md is stale; run python scripts/build_rules_doc.py")

    def test_documented_thresholds_match_the_engine(self):
        from fabric_iq.models import SEVERITY_SCORE_CAP

        scoring = read("docs", "SCORING.md")
        self.assertIn(str(int(SEVERITY_SCORE_CAP[Severity.BLOCKING])), scoring)
        self.assertIn(str(int(SEVERITY_SCORE_CAP[Severity.MAJOR])), scoring)

    def test_agent_roster_size_claimed_in_readme_is_real(self):
        agents_dir = os.path.join(REPO_ROOT, ".github", "agents")
        count = len([f for f in os.listdir(agents_dir) if f.endswith(".agent.md")])
        self.assertIn(f"{count}-agent", read("README.md"))


class TestHonestyClaims(unittest.TestCase):
    def test_limitations_state_live_field_coverage_is_unverified(self):
        text = read("docs", "KNOWN_LIMITATIONS.md")
        self.assertIn("live collection is a foundation", text.lower())
        self.assertIn("not yet been verified against a live tenant", text.lower())

    def test_readme_points_at_the_limitations_before_claiming_results(self):
        self.assertIn("KNOWN_LIMITATIONS.md", read("README.md"))

    def test_core_engine_declares_no_runtime_dependency(self):
        pyproject = read("pyproject.toml")
        self.assertIn("dependencies = []", pyproject)


if __name__ == "__main__":
    unittest.main()
