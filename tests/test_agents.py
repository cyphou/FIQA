"""Multi-agent environment integrity.

The agent files are executable documentation: they route work and declare
ownership. Drift here is silent until someone edits a module nobody owns.
"""

import os
import re
import shutil
import tempfile
import unittest

from tests.helpers import REPO_ROOT

AGENTS_DIR = os.path.join(REPO_ROOT, ".github", "agents")

EXPECTED_AGENTS = {
    "orchestrator", "collector", "scorer", "tenant", "semantic", "dataagent",
    "preceptor", "change-preceptor", "remediation", "lakehouse", "tester",
    "readme", "roadmap-planner", "security",
}

# A backticked agent invocation such as `@scorer` or `@change-preceptor`.
_MENTION = re.compile(r"`@([a-z][a-z-]*)`")


def mentioned_agents(path):
    """Agent names invoked in a document, as `@name`."""
    return set(_MENTION.findall(read(path)))


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

    def test_copilot_instructions_list_every_agent(self):
        # copilot-instructions.md is the roster the model actually reads at prompt
        # time. An agent that exists on disk but is missing here is unreachable in
        # practice, and two agents whose names share a stem (`@preceptor` reviews a
        # run, `@change-preceptor` reviews a change) are the easiest pair to drop.
        path = os.path.join(REPO_ROOT, ".github", "copilot-instructions.md")
        missing = sorted(EXPECTED_AGENTS - mentioned_agents(path))
        self.assertEqual(missing, [], f"agents absent from copilot-instructions.md: {missing}")

    def test_a_roster_missing_an_agent_is_detected(self):
        # Non-vacuity proof for the gate above: the mention parser must report an
        # omission rather than quietly returning every name it happens to see.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = os.path.join(tmp, "roster.md")
            listed = sorted(EXPECTED_AGENTS - {"change-preceptor"})
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("Invoke a specialist with `@name`.\n\n")
                handle.write(" ".join(f"`@{agent}`" for agent in listed) + "\n")

            self.assertEqual(
                sorted(EXPECTED_AGENTS - mentioned_agents(path)), ["change-preceptor"]
            )


class TestOwnership(unittest.TestCase):
    def test_every_module_is_claimed_exactly_once(self):
        from scripts.check_agent_ownership import audit

        unclaimed, duplicated = audit()
        self.assertEqual(unclaimed, [], f"modules with no owner: {unclaimed}")
        self.assertEqual(duplicated, {}, f"modules with several owners: {duplicated}")

    def test_every_gate_script_is_claimed_exactly_once(self):
        # A gate script is audited on the same terms as a package module: an
        # unowned gate fails open in silence, with no agent accountable for it.
        from scripts.check_agent_ownership import claims, script_modules

        scripts = script_modules()
        self.assertIn(
            "scripts/check_agent_ownership.py",
            scripts,
            "the gate must audit itself, otherwise this test passes vacuously",
        )
        owners = claims()
        for module in sorted(scripts):
            with self.subTest(module=module):
                self.assertEqual(
                    len(owners.get(module, [])), 1, f"{module}: {owners.get(module, [])}"
                )

    def test_the_audited_universe_spans_the_package_and_the_scripts(self):
        from scripts.check_agent_ownership import (
            audited_modules,
            package_modules,
            script_modules,
        )

        universe = audited_modules()
        self.assertTrue(package_modules() < universe)
        self.assertTrue(script_modules() <= universe)

    def test_preceptor_owns_the_review_loop(self):
        from scripts.check_agent_ownership import claims

        self.assertEqual(claims().get("fabric_iq/preceptor.py"), ["preceptor"])

    def test_security_agent_owns_no_module(self):
        from scripts.check_agent_ownership import claims

        owned = [m for m, agents in claims().items() if "security" in agents]
        self.assertEqual(owned, [], "the security agent must stay read-only")

    def test_change_preceptor_agent_owns_no_module(self):
        # @change-preceptor reviews code changes before they land. Its value is
        # that it cannot edit what it reviews, so it owns nothing -- and the
        # ownership parser reads any backticked path in the claim block as a
        # claim, so a single added line would silently hand it a module.
        from scripts.check_agent_ownership import claims

        self.assertIn(
            "change-preceptor",
            agent_files(),
            "the agent file must exist, otherwise this gate passes vacuously",
        )
        owned = [m for m, agents in claims().items() if "change-preceptor" in agents]
        self.assertEqual(owned, [], "the change-preceptor agent must stay read-only")

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

    def test_the_agent_facing_skill_has_an_accountable_owner(self):
        # A Skill is read by a model as authoritative instruction at prompt time.
        # It is not generated, so its product limits and score caps go stale in
        # silence unless a named agent answers for them.
        from scripts.check_agent_ownership import REQUIRED_DOCS

        self.assertEqual(
            REQUIRED_DOCS.get(".github/skills/fabric-iq-readiness/SKILL.md"), "readme"
        )

    def test_the_api_reality_matrix_has_an_accountable_owner(self):
        # It states what the collectors can and cannot acquire from a live tenant.
        # That claim goes stale the moment a collector gains or loses an endpoint,
        # and only the agent that owns fabric_iq/collectors/ can answer for it.
        from scripts.check_agent_ownership import REQUIRED_DOCS

        self.assertEqual(REQUIRED_DOCS.get("docs/API_REALITY_MATRIX.md"), "collector")

    def test_the_collector_has_claimed_the_api_reality_matrix(self):
        from scripts.check_agent_ownership import claims

        self.assertEqual(
            claims().get("docs/API_REALITY_MATRIX.md"),
            ["collector"],
            "docs/API_REALITY_MATRIX.md must be claimed exactly once, by @collector, "
            "in the 'Your Files (You Own These)' block of "
            ".github/agents/collector.agent.md",
        )

    def test_dropping_the_collector_claim_fails_the_document_audit(self):
        # Non-vacuity proof against the real agent tree: with the claim line
        # removed the audit must name the document and its accountable owner,
        # otherwise the REQUIRED_DOCS entry enforces nothing.
        from scripts.check_agent_ownership import REQUIRED_DOCS, audit_docs

        doc = "docs/API_REALITY_MATRIX.md"
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            agents = os.path.join(tmp, "agents")
            shutil.copytree(AGENTS_DIR, agents)
            path = os.path.join(agents, "collector.agent.md")
            text = read(path)
            self.assertIn(f"`{doc}`", text, "the claim must exist before it is removed")

            self.assertEqual(audit_docs(agents, REPO_ROOT), ([], {}, {}))

            kept = [line for line in text.splitlines(True) if f"`{doc}`" not in line]
            with open(path, "w", encoding="utf-8") as handle:
                handle.writelines(kept)

            unclaimed, duplicated, misassigned = audit_docs(agents, REPO_ROOT)

            self.assertEqual(unclaimed, [doc])
            self.assertEqual((duplicated, misassigned), ({}, {}))
            self.assertEqual(REQUIRED_DOCS[doc], "collector")

    def test_the_api_reality_matrix_disappearing_is_reported(self):
        from scripts.check_agent_ownership import missing_docs

        required = {"docs/API_REALITY_MATRIX.md": "collector"}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            os.makedirs(os.path.join(root, "docs"))
            self.assertEqual(missing_docs(root, required), list(required))

            with open(
                os.path.join(root, "docs", "API_REALITY_MATRIX.md"), "w", encoding="utf-8"
            ) as handle:
                handle.write("# API Reality Matrix\n")
            self.assertEqual(missing_docs(root, required), [])

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

    def write_script(self, name):
        directory = os.path.join(self.root, "scripts")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
            handle.write("# synthetic gate script\n")

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

    def test_a_dot_directory_path_is_recognised_as_a_claim(self):
        # `.github/skills/.../SKILL.md` must parse: before the leading dot was
        # accepted the token was read as `github/skills/...` and matched nothing,
        # so an owned Skill reported as unclaimed forever.
        from scripts.check_agent_ownership import audit_docs

        required = {".github/skills/demo/SKILL.md": "readme"}
        self.write_agent(
            "readme", ["- `.github/skills/demo/SKILL.md` — agent-facing skill"]
        )

        self.assertEqual(audit_docs(self.agents, self.root, required), ([], {}, {}))

    def test_a_dot_directory_style_claim_covers_the_files_inside_it(self):
        from scripts.check_agent_ownership import audit_docs

        required = {".github/skills/demo/SKILL.md": "readme"}
        self.write_agent("readme", ["- `.github/skills/` — every agent-facing skill"])

        self.assertEqual(audit_docs(self.agents, self.root, required), ([], {}, {}))

    def test_a_bare_suffix_in_backticks_is_not_read_as_a_path(self):
        # Prose about the parser itself writes `.py` and `.md`; reading a suffix
        # as a claim would hand a phantom path to whoever described the rule.
        from scripts.check_agent_ownership import claims

        self.write_agent(
            "readme",
            [
                "- `docs/PRIVACY.md` — retention claim",
                "- a claim ends in `.py`/`.md`, and `.gitignore` is not one",
            ],
        )

        claimed = claims(self.agents, self.root, self.required)

        for token in (".py", ".md", ".gitignore"):
            with self.subTest(token=token):
                self.assertNotIn(token, claimed)

    def test_the_module_audit_still_reports_an_unclaimed_module(self):
        from scripts.check_agent_ownership import audit

        self.write_agent("readme", ["- `docs/PRIVACY.md` — retention claim"])

        unclaimed, duplicated = audit(self.agents, self.root)

        self.assertEqual(unclaimed, ["fabric_iq/scoring.py"])
        self.assertEqual(duplicated, {})

    def test_an_unclaimed_script_is_reported_unclaimed(self):
        # The point of widening the universe to `scripts/`. Without this test the
        # widening is itself unverified, and an unowned gate -- worse than an
        # unowned module, because it fails open -- would pass unnoticed.
        from scripts.check_agent_ownership import audit

        self.write_script("check_gate.py")
        self.write_agent("tester", ["- `fabric_iq/scoring.py` — scoring"])

        unclaimed, duplicated = audit(self.agents, self.root)

        self.assertEqual(unclaimed, ["scripts/check_gate.py"])
        self.assertEqual(duplicated, {})

    def test_a_doubly_claimed_script_is_reported(self):
        from scripts.check_agent_ownership import audit

        self.write_script("check_gate.py")
        self.write_agent(
            "tester",
            ["- `fabric_iq/scoring.py` — scoring", "- `scripts/check_gate.py` — gate"],
        )
        self.write_agent("readme", ["- `scripts/check_gate.py` — also mine"])

        unclaimed, duplicated = audit(self.agents, self.root)

        self.assertEqual(unclaimed, [])
        self.assertEqual(duplicated, {"scripts/check_gate.py": ["readme", "tester"]})

    def test_a_scripts_directory_claim_covers_every_script(self):
        from scripts.check_agent_ownership import audit

        self.write_script("__init__.py")
        self.write_script("check_gate.py")
        self.write_agent(
            "tester",
            ["- `fabric_iq/scoring.py` — scoring", "- `scripts/` — every gate script"],
        )

        self.assertEqual(audit(self.agents, self.root), ([], {}))

    def test_the_scripts_package_marker_is_audited(self):
        # `__init__.py` carries no logic, but it is what makes the gates
        # importable from the suite; excluding it would leave a file nobody owns.
        from scripts.check_agent_ownership import script_modules

        self.write_script("__init__.py")

        self.assertEqual(script_modules(self.root), {"scripts/__init__.py"})



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
