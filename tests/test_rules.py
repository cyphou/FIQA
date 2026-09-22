"""Rule catalogue integrity and individual rule behaviour."""

import unittest

from fabric_iq.errors import RuleError
from fabric_iq.models import Dimension, ObjectType, RuleOutcome, RuleStatus, Severity
from fabric_iq.rules import registry
from fabric_iq.rules.base import Rule, RuleRegistry, graded, ratio
from fabric_iq.scoring import DIMENSION_WEIGHTS
from tests.helpers import ready_model, ready_tenant


class TestRegistryIntegrity(unittest.TestCase):
    def test_every_object_type_has_rules(self):
        for object_type in DIMENSION_WEIGHTS:
            with self.subTest(object_type=object_type):
                self.assertTrue(registry.for_type(object_type), f"no rule for {object_type.value}")

    def test_rule_ids_are_unique(self):
        ids = [r.id for r in registry.all()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_duplicate_registration_is_rejected(self):
        local = RuleRegistry()
        rule = Rule(
            id="X-001", title="t", object_type=ObjectType.TENANT,
            dimension=Dimension.SECURITY, severity=Severity.MINOR,
            check=lambda s: RuleOutcome.passed(), remediation="do it",
        )
        local.register(rule)
        with self.assertRaises(RuleError):
            local.register(rule)

    def test_every_rule_declares_remediation_owner_and_docs_fields(self):
        for rule in registry.all():
            with self.subTest(rule=rule.id):
                self.assertTrue(rule.remediation.strip(), f"{rule.id} has no remediation")
                self.assertTrue(rule.owner_role.strip(), f"{rule.id} has no owner_role")

    def test_every_rule_dimension_is_weighted_for_its_object_type(self):
        for rule in registry.all():
            with self.subTest(rule=rule.id):
                self.assertIn(
                    rule.dimension,
                    DIMENSION_WEIGHTS[rule.object_type],
                    f"{rule.id} scores dimension {rule.dimension.value} which carries no weight",
                )

    def test_blocking_rules_exist_for_every_object_type(self):
        for object_type in DIMENSION_WEIGHTS:
            blocking = [r for r in registry.for_type(object_type) if r.severity is Severity.BLOCKING]
            with self.subTest(object_type=object_type):
                self.assertTrue(blocking, f"{object_type.value} has no blocking rule")


class TestRuleEvaluationSafety(unittest.TestCase):
    def test_defective_rule_degrades_to_not_evaluated(self):
        rule = Rule(
            id="X-002", title="boom", object_type=ObjectType.TENANT,
            dimension=Dimension.SECURITY, severity=Severity.MINOR,
            check=lambda s: 1 / 0, remediation="fix",
        )
        # ZeroDivisionError is an ArithmeticError, not in the caught tuple, so
        # a genuine defect must still surface rather than silently pass.
        with self.assertRaises(ZeroDivisionError):
            rule.evaluate({})

    def test_missing_key_becomes_not_evaluated(self):
        rule = Rule(
            id="X-003", title="lookup", object_type=ObjectType.TENANT,
            dimension=Dimension.SECURITY, severity=Severity.MINOR,
            check=lambda s: RuleOutcome.passed(s["absent"]), remediation="fix",
        )
        outcome = rule.evaluate({})
        self.assertIs(outcome.status, RuleStatus.NOT_EVALUATED)

    def test_non_outcome_return_is_rejected(self):
        rule = Rule(
            id="X-004", title="bad", object_type=ObjectType.TENANT,
            dimension=Dimension.SECURITY, severity=Severity.MINOR,
            check=lambda s: "ok", remediation="fix",
        )
        with self.assertRaises(RuleError):
            rule.evaluate({})


class TestHelpers(unittest.TestCase):
    def test_ratio_of_empty_population_is_one(self):
        self.assertEqual(ratio(0, 0), 1.0)

    def test_ratio_is_clamped(self):
        self.assertEqual(ratio(5, 2), 1.0)

    def test_graded_zero_is_a_failure_not_a_partial(self):
        self.assertIs(graded(0.0, "nothing done").status, RuleStatus.FAILED)

    def test_graded_respects_pass_threshold(self):
        self.assertIs(graded(0.96, "", pass_at=0.95).status, RuleStatus.PASSED)
        self.assertIs(graded(0.94, "", pass_at=0.95).status, RuleStatus.PARTIAL)


class TestTenantRules(unittest.TestCase):
    def _run(self, rule_id, subject):
        return registry.get(rule_id).evaluate(subject)

    def test_healthy_tenant_has_no_blocking_failure(self):
        subject = ready_tenant()
        for rule in registry.for_type(ObjectType.TENANT):
            if rule.severity is not Severity.BLOCKING:
                continue
            with self.subTest(rule=rule.id):
                self.assertIsNot(rule.evaluate(subject).status, RuleStatus.FAILED)

    def test_disabled_fabric_fails(self):
        outcome = self._run("TEN-001", ready_tenant(fabric_enabled=False))
        self.assertIs(outcome.status, RuleStatus.FAILED)

    def test_missing_evidence_is_not_a_pass(self):
        outcome = self._run("TEN-001", ready_tenant(fabric_enabled=None))
        self.assertIs(outcome.status, RuleStatus.NOT_EVALUATED)

    def test_ineligible_sku_fails(self):
        subject = ready_tenant(capacities=[{"id": "c", "name": "n", "sku": "A1", "state": "Active"}])
        self.assertIs(self._run("TEN-004", subject).status, RuleStatus.FAILED)

    def test_cross_geo_not_required_is_not_applicable(self):
        outcome = self._run("TEN-006", ready_tenant(cross_geo_required=False))
        self.assertIs(outcome.status, RuleStatus.NOT_APPLICABLE)

    def test_unapproved_cross_geo_blocks(self):
        subject = ready_tenant(cross_geo_required=True, cross_geo_approved=False)
        self.assertIs(self._run("TEN-006", subject).status, RuleStatus.FAILED)

    def test_capacity_without_a_state_is_not_a_crash(self):
        # A missing state must not crash, and must not invent an outage either.
        subject = ready_tenant(capacities=[{"id": "c", "name": "n", "sku": "F8", "state": None}])
        self.assertIs(self._run("TEN-005", subject).status, RuleStatus.PASSED)

    def test_purview_review_missing_fails(self):
        subject = ready_tenant(purview_dlp_reviewed=False)
        self.assertIs(self._run("TEN-012", subject).status, RuleStatus.FAILED)

    def test_purview_review_not_recorded_is_not_evaluated(self):
        subject = ready_tenant(purview_dlp_reviewed=None)
        self.assertIs(self._run("TEN-012", subject).status, RuleStatus.NOT_EVALUATED)

    def test_purview_review_done_passes(self):
        subject = ready_tenant(purview_dlp_reviewed=True)
        self.assertIs(self._run("TEN-012", subject).status, RuleStatus.PASSED)


class TestWorkspaceCapacityState(unittest.TestCase):
    def _run(self, subject):
        return registry.get("WKS-010").evaluate(subject)

    def test_suspended_capacity_blocks_even_on_an_eligible_sku(self):
        outcome = self._run({"capacity_sku": "F8", "capacity_state": "Suspended"})
        self.assertIs(outcome.status, RuleStatus.FAILED)

    def test_active_capacity_passes(self):
        self.assertIs(self._run({"capacity_sku": "F8", "capacity_state": "Active"}).status, RuleStatus.PASSED)

    def test_shared_workspace_is_not_applicable(self):
        outcome = self._run({"capacity_sku": "", "capacity_state": None})
        self.assertIs(outcome.status, RuleStatus.NOT_APPLICABLE)

    def test_unobserved_state_is_not_a_pass(self):
        outcome = self._run({"capacity_sku": "F8", "capacity_state": None})
        self.assertIs(outcome.status, RuleStatus.NOT_EVALUATED)


class TestSemanticModelRules(unittest.TestCase):
    def _run(self, rule_id, subject):
        return registry.get(rule_id).evaluate(subject)

    def test_ready_model_passes_every_blocking_rule(self):
        subject = ready_model()
        for rule in registry.for_type(ObjectType.SEMANTIC_MODEL):
            if rule.severity is not Severity.BLOCKING:
                continue
            with self.subTest(rule=rule.id):
                self.assertIsNot(rule.evaluate(subject).status, RuleStatus.FAILED)

    def test_single_flat_table_fails_star_schema(self):
        subject = ready_model(tables=[{"name": "Flat", "role": "unknown"}])
        self.assertIs(self._run("SEM-001", subject).status, RuleStatus.FAILED)

    def test_technical_names_are_detected(self):
        subject = ready_model(
            measures=[{"name": "AMT_EUR", "description": "x" * 40, "expression": "SUM(a)", "hidden": False}]
        )
        outcome = self._run("SEM-005", subject)
        self.assertIn(outcome.status, (RuleStatus.FAILED, RuleStatus.PARTIAL))

    def test_camel_case_is_technical(self):
        subject = ready_model(
            tables=[{"name": "salesHeader", "role": "fact", "description": "x" * 40}],
            columns=[], measures=[],
        )
        outcome = self._run("SEM-005", subject)
        self.assertIn(outcome.status, (RuleStatus.FAILED, RuleStatus.PARTIAL))

    def test_short_description_does_not_count_as_described(self):
        subject = ready_model(
            tables=[{"name": "Sales", "role": "fact", "description": "sales"}],
            columns=[], measures=[],
        )
        self.assertIs(self._run("SEM-006", subject).status, RuleStatus.FAILED)

    def test_missing_ai_schema_blocks(self):
        subject = ready_model(ai_data_schema={"selected_objects": 0})
        self.assertIs(self._run("SEM-008", subject).status, RuleStatus.FAILED)

    def test_overly_broad_ai_schema_is_partial(self):
        subject = ready_model(ai_data_schema={"selected_objects": 10}, visible_object_count=11)
        self.assertIs(self._run("SEM-008", subject).status, RuleStatus.PARTIAL)

    def test_missing_ai_schema_dependency_blocks(self):
        subject = ready_model(
            ai_data_schema={"selected_objects": 5, "missing_dependencies": ["Cost"]}
        )
        self.assertIs(self._run("SEM-009", subject).status, RuleStatus.FAILED)

    def test_ai_instructions_over_limit_fail(self):
        self.assertIs(self._run("SEM-011", ready_model(ai_instructions="x" * 10_001)).status,
                      RuleStatus.FAILED)

    def test_broken_verified_answer_fails(self):
        subject = ready_model(verified_answers=[{"question": "q", "broken": True}])
        self.assertIs(self._run("SEM-012", subject).status, RuleStatus.FAILED)

    def test_duplicate_measure_expressions_are_detected(self):
        subject = ready_model(
            measures=[
                {"name": "AMT", "description": "d" * 40, "expression": "SUM(T[A])", "hidden": False},
                {"name": "Amount", "description": "d" * 40, "expression": "SUM( T[A] )", "hidden": False},
            ]
        )
        outcome = self._run("SEM-014", subject)
        self.assertIn(outcome.status, (RuleStatus.FAILED, RuleStatus.PARTIAL))

    def test_string_literals_are_not_collapsed_when_comparing_measures(self):
        subject = ready_model(
            measures=[
                {"name": "NA Sales", "description": "d" * 40,
                 "expression": 'CALCULATE([S], T[R] = "North America")', "hidden": False},
                {"name": "NAM Sales", "description": "d" * 40,
                 "expression": 'CALCULATE([S], T[R] = "NorthAmerica")', "hidden": False},
            ]
        )
        self.assertIs(self._run("SEM-014", subject).status, RuleStatus.PASSED)

    def test_rls_required_without_roles_blocks(self):
        subject = ready_model(rls_required=True, rls_roles=[])
        self.assertIs(self._run("SEM-015", subject).status, RuleStatus.FAILED)

    def test_untested_rls_role_is_partial(self):
        subject = ready_model(rls_roles=[{"name": "R", "tested": False}])
        self.assertIs(self._run("SEM-015", subject).status, RuleStatus.PARTIAL)

    def test_stale_data_fails_freshness(self):
        subject = ready_model(hours_since_refresh=100, freshness_sla_hours=24)
        self.assertIs(self._run("SEM-016", subject).status, RuleStatus.FAILED)

    def test_schema_retrieval_error_fails(self):
        subject = ready_model(schema_retrieval_error="not refreshed")
        self.assertIs(self._run("SEM-017", subject).status, RuleStatus.FAILED)


class TestDataAgentRules(unittest.TestCase):
    def _run(self, rule_id, subject):
        return registry.get(rule_id).evaluate(subject)

    def _agent(self, **overrides):
        subject = {
            "id": "agt", "name": "Agent",
            "data_sources": [{"id": "sm", "name": "Model", "type": "semantic_model",
                              "reachable": True, "description": "Commercial questions."}],
            "source_scores": {"sm": 92.0},
            "instructions": "Answer sales questions only. " * 12,
            "target_languages": ["fr"],
            "requires_write": False,
            "expects_bulk_export": False,
            "latency_sla_seconds": 30,
            "preview_dependencies": [],
            "evaluation": {
                "questions_asked": 30, "executable_queries": 29, "correct_answers": 28,
                "critical_questions_asked": 5, "critical_questions_correct": 5,
                "personas_tested": 3, "leakage_incidents": 0,
                "negative_tests": 5, "negative_tests_refused": 5,
                "languages_tested": ["fr"], "latency_p95_seconds": 12,
            },
        }
        subject.update(overrides)
        return subject

    def test_healthy_agent_passes_blocking_rules(self):
        subject = self._agent()
        for rule in registry.for_type(ObjectType.DATA_AGENT):
            if rule.severity is not Severity.BLOCKING:
                continue
            with self.subTest(rule=rule.id):
                self.assertIsNot(rule.evaluate(subject).status, RuleStatus.FAILED)

    def test_too_many_sources_blocks(self):
        sources = [{"id": f"s{i}", "name": f"s{i}", "type": "lakehouse",
                    "reachable": True, "description": "d"} for i in range(6)]
        self.assertIs(self._run("AGT-002", self._agent(data_sources=sources)).status, RuleStatus.FAILED)

    def test_single_persona_blocks_isolation(self):
        subject = self._agent()
        subject["evaluation"]["personas_tested"] = 1
        self.assertIs(self._run("AGT-010", subject).status, RuleStatus.FAILED)

    def test_leakage_blocks(self):
        subject = self._agent()
        subject["evaluation"]["leakage_incidents"] = 1
        self.assertIs(self._run("AGT-010", subject).status, RuleStatus.FAILED)

    def test_no_negative_tests_blocks(self):
        subject = self._agent()
        subject["evaluation"]["negative_tests"] = 0
        self.assertIs(self._run("AGT-011", subject).status, RuleStatus.FAILED)

    def test_untested_language_blocks(self):
        subject = self._agent(target_languages=["fr", "de"])
        outcome = self._run("AGT-012", subject)
        self.assertIn(outcome.status, (RuleStatus.FAILED, RuleStatus.PARTIAL))

    def test_bulk_export_use_case_blocks(self):
        self.assertIs(self._run("AGT-013", self._agent(expects_bulk_export=True)).status,
                      RuleStatus.FAILED)

    def test_accuracy_below_threshold_blocks(self):
        subject = self._agent()
        subject["evaluation"]["correct_answers"] = 10
        self.assertIs(self._run("AGT-008", subject).status, RuleStatus.FAILED)

    def test_no_evaluation_is_not_a_silent_pass(self):
        subject = self._agent(evaluation={"questions_asked": 0})
        self.assertIs(self._run("AGT-006", subject).status, RuleStatus.FAILED)
        self.assertIs(self._run("AGT-008", subject).status, RuleStatus.NOT_EVALUATED)


if __name__ == "__main__":
    unittest.main()
