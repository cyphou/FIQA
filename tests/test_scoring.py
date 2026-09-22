"""Scoring engine invariants.

These tests pin the three-outcome contract: eligibility, readiness score and
confidence are computed independently and must never be silently merged.
"""

import unittest

from fabric_iq.models import (
    Dimension,
    Evidence,
    ObjectType,
    ReadinessStatus,
    RuleOutcome,
    RuleStatus,
    Severity,
)
from fabric_iq.rules.base import Rule, RuleRegistry
from fabric_iq.scoring import DIMENSION_WEIGHTS, ScoringEngine, assess
from tests.helpers import minimal_inventory, ready_model, ready_tenant


def run_assess(inventory):
    return assess(inventory, run_id="run_test")


def make_rule(rule_id, dimension, severity, outcome, *, object_type=ObjectType.SEMANTIC_MODEL, weight=1.0):
    return Rule(
        id=rule_id, title=rule_id, object_type=object_type, dimension=dimension,
        severity=severity, check=lambda s, o=outcome: o, remediation="fix it",
        weight=weight, owner_role="Test",
    )


class TestObjectScoring(unittest.TestCase):
    def score(self, rules, subject=None):
        registry = RuleRegistry()
        for rule in rules:
            registry.register(rule)
        engine = ScoringEngine(rules=registry)
        return engine.score_object(subject or {"id": "o", "name": "O"}, ObjectType.SEMANTIC_MODEL)

    def test_all_pass_is_a_hundred_and_ready(self):
        rules = [
            make_rule("A", dim, Severity.MINOR, RuleOutcome.passed("ok"))
            for dim in DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL]
        ]
        for index, rule in enumerate(rules):
            object.__setattr__(rule, "id", f"A{index}")
        card = self.score(rules)
        self.assertEqual(card.score, 100.0)
        self.assertIs(card.status, ReadinessStatus.READY)
        self.assertTrue(card.eligible)

    def test_blocking_failure_caps_score_and_revokes_eligibility(self):
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        rules = [make_rule(f"P{i}", d, Severity.MINOR, RuleOutcome.passed("ok")) for i, d in enumerate(dims)]
        rules.append(make_rule("B1", dims[0], Severity.BLOCKING, RuleOutcome.failed("broken")))
        card = self.score(rules)
        self.assertLessEqual(card.score, 39.0)
        self.assertIs(card.status, ReadinessStatus.NOT_READY)
        self.assertFalse(card.eligible)

    def test_major_failure_caps_at_fifty_nine_but_keeps_eligibility(self):
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        rules = [make_rule(f"P{i}", d, Severity.MINOR, RuleOutcome.passed("ok")) for i, d in enumerate(dims)]
        rules.append(make_rule("M1", dims[0], Severity.MAJOR, RuleOutcome.failed("weak")))
        card = self.score(rules)
        self.assertLessEqual(card.score, 59.0)
        self.assertTrue(card.eligible)

    def test_cap_never_raises_a_lower_score(self):
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        rules = [make_rule(f"F{i}", d, Severity.MINOR, RuleOutcome.failed("no")) for i, d in enumerate(dims)]
        rules.append(make_rule("M1", dims[0], Severity.MAJOR, RuleOutcome.failed("weak")))
        card = self.score(rules)
        self.assertLess(card.score, 59.0)

    def test_not_evaluated_is_neither_pass_nor_zero(self):
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        passing = [make_rule(f"P{i}", d, Severity.MINOR, RuleOutcome.passed("ok")) for i, d in enumerate(dims)]
        unknown = make_rule("U1", dims[0], Severity.MAJOR, RuleOutcome.not_evaluated("no evidence"))
        card = self.score(passing + [unknown])
        self.assertEqual(card.score, 100.0, "an unknown rule must not drag the score down")
        self.assertLess(card.confidence, 100.0, "an unknown rule must lower confidence")

    def test_low_coverage_forces_not_evaluated_status(self):
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        rules = [make_rule(f"U{i}", d, Severity.MINOR, RuleOutcome.not_evaluated("none")) for i, d in enumerate(dims)]
        rules.append(make_rule("P1", dims[0], Severity.MINOR, RuleOutcome.passed("ok")))
        card = self.score(rules)
        self.assertIs(card.status, ReadinessStatus.NOT_EVALUATED)

    def test_blocking_finding_still_caps_when_coverage_is_below_the_floor(self):
        # A wall is positive evidence. Thin coverage means we cannot judge quality,
        # never that the wall stopped existing, so it must not publish an uncapped score.
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        rules = [
            make_rule(f"U{i}", d, Severity.MINOR, RuleOutcome.not_evaluated("none"))
            for i, d in enumerate(dims)
        ]
        rules.append(make_rule("P1", dims[0], Severity.MINOR, RuleOutcome.passed("ok")))
        rules.append(make_rule("B1", dims[0], Severity.BLOCKING, RuleOutcome.failed("wall")))
        card = self.score(rules)
        self.assertIs(card.status, ReadinessStatus.NOT_READY)
        self.assertFalse(card.eligible)
        self.assertLessEqual(card.score, 39.0)
        self.assertLess(card.coverage, 0.5, "the guard is only meaningful below the floor")

    def test_no_rule_evaluated_yields_zero_confidence_not_a_crash(self):
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        rules = [make_rule(f"U{i}", d, Severity.MINOR, RuleOutcome.not_evaluated("none")) for i, d in enumerate(dims)]
        card = self.score(rules)
        self.assertEqual(card.confidence, 0.0)
        self.assertIs(card.status, ReadinessStatus.NOT_EVALUATED)

    def test_not_applicable_does_not_penalise_score_or_confidence(self):
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        rules = [make_rule(f"P{i}", d, Severity.MINOR, RuleOutcome.passed("ok")) for i, d in enumerate(dims)]
        baseline = self.score(rules).confidence
        rules.append(make_rule("NA1", dims[0], Severity.BLOCKING, RuleOutcome.not_applicable("out of scope")))
        card = self.score(rules)
        self.assertEqual(card.score, 100.0)
        self.assertEqual(card.confidence, baseline)
        self.assertTrue(card.eligible)

    def test_unobservable_dimension_lowers_confidence_not_score(self):
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        observed = [make_rule(f"P{i}", d, Severity.MINOR, RuleOutcome.passed("ok"))
                    for i, d in enumerate(dims[:-1])]
        blind = make_rule("U1", dims[-1], Severity.MINOR, RuleOutcome.not_evaluated("no evidence"))
        card = self.score(observed + [blind])
        self.assertEqual(card.score, 100.0)
        self.assertLess(card.confidence, 100.0)

    def test_partial_outcome_produces_a_middling_score(self):
        dims = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])
        rules = [make_rule(f"H{i}", d, Severity.MINOR, RuleOutcome.partial(0.5, "half"))
                 for i, d in enumerate(dims)]
        card = self.score(rules)
        self.assertAlmostEqual(card.score, 50.0, places=4)

    def test_rule_weight_is_respected_within_a_dimension(self):
        dim = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])[0]
        heavy = make_rule("H", dim, Severity.MINOR, RuleOutcome.failed("no"), weight=9.0)
        light = make_rule("L", dim, Severity.MINOR, RuleOutcome.passed("ok"), weight=1.0)
        card = self.score([heavy, light])
        self.assertAlmostEqual(card.score, 10.0, places=4)

    def test_findings_keep_the_full_audit_trail_but_expose_failures(self):
        dim = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])[0]
        rules = [
            make_rule("F", dim, Severity.MAJOR, RuleOutcome.failed("bad")),
            make_rule("P", dim, Severity.MAJOR, RuleOutcome.passed("good")),
            make_rule("N", dim, Severity.MAJOR, RuleOutcome.not_applicable("skip")),
        ]
        card = self.score(rules)
        self.assertEqual({f.rule_id for f in card.findings}, {"F", "P", "N"})
        self.assertEqual([f.rule_id for f in card.failed_findings], ["F"])
        self.assertEqual(card.blocking_findings, [])

    def test_finding_carries_remediation_and_evidence(self):
        dim = list(DIMENSION_WEIGHTS[ObjectType.SEMANTIC_MODEL])[0]
        outcome = RuleOutcome.failed("bad", evidence=[Evidence(source="scanner_api", reference="x")])
        card = self.score([make_rule("F", dim, Severity.BLOCKING, outcome)])
        finding = card.failed_findings[0]
        self.assertEqual(finding.remediation, "fix it")
        self.assertEqual(finding.outcome.evidence[0].source, "scanner_api")


class TestRollups(unittest.TestCase):
    def test_blocking_child_caps_the_parent(self):
        inventory = minimal_inventory(
            workspaces=[{
                "id": "ws", "name": "WS", "parent_id": "tenant-test",
                "capacity_sku": "F64", "is_pro": False,
            }],
            semantic_models=[ready_model(id="sm", parent_id="ws", rls_required=True, rls_roles=[])],
        )
        run = run_assess(inventory)
        workspace = next(c for c in run.scorecards if c.object_type is ObjectType.WORKSPACE)
        self.assertLessEqual(workspace.score, 59.0)

    def test_tenant_scorecard_always_exists(self):
        run = run_assess(minimal_inventory())
        self.assertTrue(any(c.object_type is ObjectType.TENANT for c in run.scorecards))

    def test_orphan_object_does_not_crash_the_rollup(self):
        inventory = minimal_inventory(
            semantic_models=[ready_model(id="sm", parent_id="missing-workspace")]
        )
        run = run_assess(inventory)
        self.assertTrue(run.scorecards)


class TestAssessRun(unittest.TestCase):
    def test_run_is_reproducible(self):
        inventory = minimal_inventory(semantic_models=[ready_model()])
        first = {c.object_id: c.score for c in run_assess(inventory).scorecards}
        second = {c.object_id: c.score for c in run_assess(inventory).scorecards}
        self.assertEqual(first, second)

    def test_scores_are_bounded(self):
        inventory = minimal_inventory(semantic_models=[ready_model(), ready_model(id="sm2", tables=[])])
        for card in run_assess(inventory).scorecards:
            with self.subTest(obj=card.object_id):
                self.assertGreaterEqual(card.score, 0.0)
                self.assertLessEqual(card.score, 100.0)
                self.assertGreaterEqual(card.confidence, 0.0)
                self.assertLessEqual(card.confidence, 100.0)

    def test_blocking_findings_are_surfaced_at_run_level(self):
        inventory = minimal_inventory(
            semantic_models=[ready_model(rls_required=True, rls_roles=[])]
        )
        run = run_assess(inventory)
        self.assertTrue([f for f in run.blocking_findings])

    def test_blocking_findings_are_serialised_for_readers(self):
        """The skill tells readers to open `blocking_findings` first; it must exist."""
        inventory = minimal_inventory(
            semantic_models=[ready_model(rls_required=True, rls_roles=[])]
        )
        payload = run_assess(inventory).to_dict()
        self.assertTrue(payload["blocking_findings"], "run-level walls must be serialised")
        blocked = [c for c in payload["scorecards"] if c["blocking_findings"]]
        self.assertTrue(blocked, "the owning scorecard must point at its blocking rules")
        self.assertIn(
            blocked[0]["blocking_findings"][0],
            [f["rule_id"] for f in blocked[0]["findings"]],
            "the scorecard index must reference a rule present in its findings",
        )

    def test_ruleset_version_is_recorded(self):
        run = run_assess(minimal_inventory())
        self.assertTrue(run.ruleset_version)

    def test_agent_with_unknown_sources_is_not_evaluated_rather_than_crashing(self):
        """`data_sources: None` means unobserved, not empty: it must not be iterated."""
        inventory = minimal_inventory(
            data_agents=[{"id": "a1", "name": "Agent", "parent_id": "w1", "data_sources": None}]
        )
        run = run_assess(inventory)
        card = next(c for c in run.scorecards if c.object_id == "a1")
        self.assertEqual(card.status, ReadinessStatus.NOT_EVALUATED)

    def test_unobserved_collections_do_not_crash_the_run(self):
        """A present-but-None collection means unobserved; assess must still produce a run."""
        inventory = minimal_inventory(
            workspaces=None, semantic_models=None, reports=None,
            data_agents=None, collection_errors=None,
        )
        run = run_assess(inventory)
        self.assertTrue(
            [c for c in run.scorecards if c.object_type is ObjectType.TENANT],
            "the tenant must still be scored when nothing else was observed",
        )


if __name__ == "__main__":
    unittest.main()
