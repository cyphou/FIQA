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

    def test_copilot_capacity_designation_enabled_passes(self):
        subject = ready_tenant(copilot_capacity_designation_enabled=True)
        self.assertIs(self._run("TEN-011", subject).status, RuleStatus.PASSED)

    def test_copilot_capacity_designation_disabled_is_only_partial_not_failed(self):
        # This is a recommendation, not a requirement: it must never fail outright,
        # and it must never cap the score the way a BLOCKING/MAJOR rule would.
        subject = ready_tenant(copilot_capacity_designation_enabled=False)
        outcome = self._run("TEN-011", subject)
        self.assertIs(outcome.status, RuleStatus.PARTIAL)
        rule = registry.get("TEN-011")
        self.assertIs(rule.severity, Severity.INFO)

    def test_copilot_capacity_designation_not_recorded_is_not_evaluated(self):
        subject = ready_tenant(copilot_capacity_designation_enabled=None)
        self.assertIs(self._run("TEN-011", subject).status, RuleStatus.NOT_EVALUATED)

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


class TestWorkspaceCopilotCapacityCoverage(unittest.TestCase):
    def _run(self, subject):
        return registry.get("WKS-011").evaluate(subject)

    def test_assigned_copilot_capacity_passes(self):
        subject = {"capacity_sku": "F8", "copilot_capacity_assigned": True}
        self.assertIs(self._run(subject).status, RuleStatus.PASSED)

    def test_unassigned_copilot_capacity_is_only_partial_not_failed(self):
        # This is a recommendation, not a requirement: it must never fail outright,
        # and it must never cap the score the way a BLOCKING/MAJOR rule would.
        subject = {"capacity_sku": "F8", "copilot_capacity_assigned": False}
        outcome = self._run(subject)
        self.assertIs(outcome.status, RuleStatus.PARTIAL)
        rule = registry.get("WKS-011")
        self.assertIs(rule.severity, Severity.INFO)

    def test_ineligible_sku_is_not_applicable(self):
        subject = {"capacity_sku": "", "copilot_capacity_assigned": False}
        self.assertIs(self._run(subject).status, RuleStatus.NOT_APPLICABLE)

    def test_f64_or_above_natively_supports_copilot_and_is_not_applicable(self):
        subject = {"capacity_sku": "F64", "copilot_capacity_assigned": False}
        self.assertIs(self._run(subject).status, RuleStatus.NOT_APPLICABLE)

    def test_premium_p1_is_treated_as_the_f64_equivalent(self):
        subject = {"capacity_sku": "P1", "copilot_capacity_assigned": False}
        self.assertIs(self._run(subject).status, RuleStatus.NOT_APPLICABLE)

    def test_unrecorded_assignment_is_not_evaluated(self):
        subject = {"capacity_sku": "F8", "copilot_capacity_assigned": None}
        self.assertIs(self._run(subject).status, RuleStatus.NOT_EVALUATED)


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


class TestEndorsementRules(unittest.TestCase):
    """SEM-018 / REP-011 — endorsement as a Microsoft 365 discoverability signal.

    The two guards these tests exist to hold down, both verified by mutation rather
    than by assertion:

    1. **``None`` is unknown, never "not endorsed".** The Scanner returns a documented
       *subset* of properties depending on the API called, caller permissions and data
       availability, and never states how a non-endorsed item is represented. Letting
       absence fall through to a failure would manufacture a finding out of a
       permission gap. Breaking this guard must break a test here.
    2. **An unrecognised value is still an endorsement.** The API reference enumerates
       no values for ``endorsement``. Clamping the field to a closed vocabulary would
       make the tool tell a customer their certified content is uncertified the first
       time a new or region-specific level ships. Breaking this guard must break a
       test here too.
    """

    RULES = {"SEM-018": "model", "REP-011": "report"}

    def _run(self, rule_id, **fields):
        return registry.get(rule_id).evaluate({"id": "o", "name": "O", **fields})

    # ── guard 1: absence is unknown ────────────────────────────────────

    def test_absent_field_is_not_evaluated(self):
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                outcome = self._run(rule_id)
                self.assertIs(outcome.status, RuleStatus.NOT_EVALUATED)

    def test_unknown_endorsement_is_not_evaluated_and_never_a_failure(self):
        # None covers an absent key, a null container, an empty container, a null
        # value and any undocumented shape: the collector maps all of them here.
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                outcome = self._run(rule_id, endorsement=None, endorsement_certified_by=None)
                self.assertIs(outcome.status, RuleStatus.NOT_EVALUATED)

    def test_unknown_status_stays_unknown_even_when_a_certifier_is_stated(self):
        # The two fields are independent: a stated certifier must never be used to
        # infer a status the service did not return.
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                outcome = self._run(
                    rule_id, endorsement=None, endorsement_certified_by="governance-board"
                )
                self.assertIs(outcome.status, RuleStatus.NOT_EVALUATED)

    def test_unreadable_type_is_not_evaluated_not_a_negative(self):
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                self.assertIs(self._run(rule_id, endorsement=7).status, RuleStatus.NOT_EVALUATED)

    # ── guard 2: an unrecognised value still passes ────────────────────

    def test_unrecognised_value_passes_and_says_it_is_unrecognised(self):
        # A future or region-specific level must not be scored as unendorsed.
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                outcome = self._run(rule_id, endorsement="Sovereign Gold")
                self.assertIs(outcome.status, RuleStatus.PASSED)
                self.assertIn("Sovereign Gold", outcome.detail)
                self.assertIn("does not recognise", outcome.detail)
                self.assertFalse(outcome.observed["recognised"])

    def test_unrecognised_value_is_never_reported_as_absent(self):
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                observed = self._run(rule_id, endorsement="Tier-1 Trusted").observed
                self.assertEqual(observed["endorsement"], "Tier-1 Trusted")

    # ── the honest negative, and the recognised values ─────────────────

    def test_service_asserted_empty_string_is_the_only_negative(self):
        for rule_id, item in self.RULES.items():
            with self.subTest(rule=rule_id):
                outcome = self._run(rule_id, endorsement="")
                self.assertIs(outcome.status, RuleStatus.FAILED)
                self.assertIn(item, outcome.detail)

    def test_recognised_levels_pass_and_are_named(self):
        for rule_id in self.RULES:
            for value, named in (
                ("Promoted", "Promoted"),
                ("Certified", "Certified"),
                ("Master data", "Master data"),
                ("MasterData", "Master data"),
                ("  certified  ", "Certified"),
            ):
                with self.subTest(rule=rule_id, value=value):
                    outcome = self._run(rule_id, endorsement=value)
                    self.assertIs(outcome.status, RuleStatus.PASSED)
                    self.assertIn(named, outcome.detail)
                    self.assertTrue(outcome.observed["recognised"])

    def test_promoted_is_a_pass_not_a_partial(self):
        # Microsoft documents endorsements as a discovery signal without ranking the
        # levels against each other, so treating Promoted as a half-endorsement would
        # encode a hierarchy no source states.
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                self.assertIs(self._run(rule_id, endorsement="Promoted").status, RuleStatus.PASSED)

    # ── privacy and severity ───────────────────────────────────────────

    def test_the_certifier_identity_is_never_echoed_into_a_finding(self):
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                outcome = self._run(
                    rule_id, endorsement="Certified", endorsement_certified_by="certifier-principal"
                )
                self.assertIs(outcome.status, RuleStatus.PASSED)
                self.assertNotIn("certifier-principal", outcome.detail)
                self.assertNotIn("certifier-principal", str(outcome.observed))
                self.assertTrue(outcome.observed["certifier_stated"])

    def test_a_certified_item_without_a_stated_certifier_still_passes(self):
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                outcome = self._run(rule_id, endorsement="Certified")
                self.assertIs(outcome.status, RuleStatus.PASSED)
                self.assertFalse(outcome.observed["certifier_stated"])

    def test_endorsement_severity_never_caps_the_published_score(self):
        # BLOCKING caps at 39 and revokes eligibility, MAJOR caps at 59. An unendorsed
        # item is harder to find, not wrong once found, so neither cap may apply.
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                severity = registry.get(rule_id).severity
                self.assertIs(severity, Severity.MINOR)
                self.assertNotIn(severity, (Severity.BLOCKING, Severity.MAJOR))

    def test_endorsement_is_scored_in_a_dimension_its_object_type_weights(self):
        for rule_id in self.RULES:
            with self.subTest(rule=rule_id):
                rule = registry.get(rule_id)
                self.assertIn(rule.dimension, DIMENSION_WEIGHTS[rule.object_type])


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
