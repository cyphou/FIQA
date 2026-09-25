"""Scoring engine invariants.

These tests pin the three-outcome contract: eligibility, readiness score and
confidence are computed independently and must never be silently merged.

They also pin ruleset *identity*: the version token a run stamps must identify
exactly one set of scoring inputs, or every trend view built on it is reporting
a change nobody made.
"""

import dataclasses
import re
import unittest

from fabric_iq import RULESET_VERSION
from fabric_iq.models import (
    Dimension,
    Evidence,
    ObjectType,
    ReadinessStatus,
    RuleOutcome,
    RuleStatus,
    Severity,
)
from fabric_iq.rules import registry as live_registry
from fabric_iq.rules.base import Rule, RuleRegistry
from fabric_iq.scoring import (
    AMBIGUOUS_FINGERPRINT,
    DIMENSION_WEIGHTS,
    RULESET_HISTORY,
    ScoringEngine,
    assess,
    current_release,
    fingerprint_of,
    release_for,
    ruleset_fingerprint,
    ruleset_inputs,
)
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


class TestRulesetIdentity(unittest.TestCase):
    """The version token must identify exactly one set of scoring inputs.

    Before this guard, `RULESET_VERSION` never moved while the catalogue grew
    from 61 to 67 rules. Two runs could stamp the same token, disagree about an
    unchanged estate, and `compare_runs` would call the difference an
    improvement because the comparability key said they were comparable.
    """

    def test_the_declared_version_is_published_in_the_ledger(self):
        release = current_release()

        self.assertEqual(release.version, RULESET_VERSION)

    def test_catalogue_fingerprint_matches_the_declared_version(self):
        """The load-bearing guard: the catalogue cannot move under a fixed token."""
        release = current_release()
        actual = ruleset_fingerprint()

        self.assertEqual(
            actual,
            release.fingerprint,
            "\nThe scoring inputs no longer match ruleset version "
            f"{RULESET_VERSION}.\n"
            f"  declared: {release.fingerprint} ({release.rule_count} rules)\n"
            f"  actual:   {actual} ({len(live_registry)} rules)\n"
            "A rule was added, removed, re-weighted, re-scoped or re-graded, or a "
            "dimension weight, cap, threshold or rollup moved. Any of those makes "
            "new runs incomparable with runs already stored under this version.\n"
            "Do NOT edit the existing RULESET_HISTORY entry -- that re-labels "
            "evidence somebody already has. Bump RULESET_VERSION in "
            "fabric_iq/__init__.py and APPEND a RulesetRelease with the actual "
            "fingerprint above. See docs/SCORING.md 'Ruleset Versioning'.",
        )

    def test_declared_rule_count_matches_the_registry(self):
        """A human-readable cross-check on the opaque hash."""
        self.assertEqual(current_release().rule_count, len(live_registry))

    def test_the_declared_version_is_the_newest_entry(self):
        self.assertEqual(RULESET_HISTORY[-1].version, RULESET_VERSION)

    def test_versions_are_unique_and_strictly_increasing(self):
        keys = []
        for release in RULESET_HISTORY:
            match = re.fullmatch(r"(\d{4})\.(\d{2})\.(\d+)", release.version)
            self.assertIsNotNone(
                match, f"ruleset version {release.version!r} is not YYYY.MM.N"
            )
            keys.append(tuple(int(part) for part in match.groups()))

        self.assertEqual(
            keys,
            sorted(set(keys)),
            "RULESET_HISTORY must be append-only, ordered oldest first, and never "
            "reuse a version: a reused token is the defect this ledger exists to stop",
        )

    def test_no_two_versions_claim_the_same_catalogue(self):
        fingerprints = [
            r.fingerprint for r in RULESET_HISTORY if not r.is_ambiguous
        ]

        self.assertEqual(
            len(fingerprints),
            len(set(fingerprints)),
            "two versions with one fingerprint means a version was incremented "
            "without the scoring inputs changing; that costs a run of trend signal "
            "for nothing",
        )

    def test_the_pre_policy_version_is_recorded_as_ambiguous(self):
        """2026.09.1 was stamped on several catalogues, so it identifies none."""
        legacy = release_for("2026.09.1")

        self.assertIsNotNone(legacy, "the pre-policy version must stay in the ledger")
        self.assertEqual(legacy.fingerprint, AMBIGUOUS_FINGERPRINT)
        self.assertIn("not comparable", legacy.note)

    def test_every_rule_and_engine_constant_appears_in_the_fingerprint_input(self):
        """A hash over the wrong inputs is a guard over nothing."""
        lines = ruleset_inputs()

        for rule in live_registry.all():
            with self.subTest(rule=rule.id):
                self.assertTrue(
                    any(line.startswith(f"rule\t{rule.id}\t") for line in lines),
                    f"{rule.id} is not covered by the ruleset fingerprint",
                )
        for object_type, weights in DIMENSION_WEIGHTS.items():
            for dimension in weights:
                with self.subTest(object_type=object_type.value, dimension=dimension.value):
                    self.assertTrue(
                        any(
                            line.startswith(
                                f"dimension-weight\t{object_type.value}\t{dimension.value}\t"
                            )
                            for line in lines
                        )
                    )
        for prefix in ("severity-cap\t", "status-threshold\t", "coverage-floor\t", "rollup\t"):
            with self.subTest(prefix=prefix.strip()):
                self.assertTrue(any(line.startswith(prefix) for line in lines))


class TestTheRulesetGuardActuallyFails(unittest.TestCase):
    """A guard that passes against the broken state proves nothing.

    Each test mutates the catalogue or an engine constant the way a future
    contributor would and asserts the fingerprint moves -- so the guard above
    would fail and force a version bump.
    """

    def clone(self, *, extra=(), skip=(), mutate=None):
        clone = RuleRegistry()
        for rule in live_registry.all():
            if rule.id in skip:
                continue
            clone.register(mutate(rule) if mutate else rule)
        for rule in extra:
            clone.register(rule)
        return clone

    def assert_moved(self, mutated_registry):
        self.assertNotEqual(
            ruleset_fingerprint(mutated_registry),
            current_release().fingerprint,
            "this change alters scores or confidence but left the ruleset "
            "fingerprint untouched; the guard cannot see it",
        )

    def test_the_unmutated_catalogue_still_matches(self):
        """The control: cloning alone must not move the fingerprint."""
        self.assertEqual(
            ruleset_fingerprint(self.clone()), current_release().fingerprint
        )

    def test_adding_a_rule_moves_the_fingerprint(self):
        """The exact defect: SEM-018 and REP-011 landed under a frozen token."""
        new_rule = make_rule("SEM-999", Dimension.AI_READINESS, Severity.MINOR,
                             RuleOutcome.passed("ok"))

        self.assert_moved(self.clone(extra=[new_rule]))

    def test_removing_a_rule_moves_the_fingerprint(self):
        doomed = sorted(r.id for r in live_registry.all())[0]

        self.assert_moved(self.clone(skip={doomed}))

    def test_re_grading_a_rule_to_blocking_moves_the_fingerprint(self):
        target = sorted(live_registry.all(), key=lambda r: r.id)[0]
        promoted = Severity.MAJOR if target.severity is Severity.BLOCKING else Severity.BLOCKING

        self.assert_moved(
            self.clone(
                mutate=lambda r: dataclasses.replace(r, severity=promoted)
                if r.id == target.id
                else r
            )
        )

    def test_re_weighting_a_rule_moves_the_fingerprint(self):
        target = sorted(live_registry.all(), key=lambda r: r.id)[0]

        self.assert_moved(
            self.clone(
                mutate=lambda r: dataclasses.replace(r, weight=r.weight + 0.5)
                if r.id == target.id
                else r
            )
        )

    def test_moving_a_rule_to_another_dimension_moves_the_fingerprint(self):
        target = sorted(live_registry.all(), key=lambda r: r.id)[0]
        elsewhere = next(d for d in Dimension if d is not target.dimension)

        self.assert_moved(
            self.clone(
                mutate=lambda r: dataclasses.replace(r, dimension=elsewhere)
                if r.id == target.id
                else r
            )
        )

    def test_moving_an_engine_constant_moves_the_fingerprint(self):
        """Dimension weights, caps, thresholds and rollups are inputs too."""
        for prefix in ("dimension-weight\t", "severity-cap\t", "status-threshold\t",
                       "coverage-floor\t", "rollup\t"):
            with self.subTest(constant=prefix.strip()):
                mutated = []
                bumped = False
                for line in ruleset_inputs():
                    if line.startswith(prefix) and not bumped:
                        fields = line.split("\t")
                        for index in range(len(fields) - 1, 0, -1):
                            try:
                                value = float(fields[index])
                            except ValueError:
                                continue
                            fields[index] = f"{value + 0.01:.6f}"
                            bumped = True
                            break
                        line = "\t".join(fields)
                    mutated.append(line)

                self.assertTrue(bumped, f"no numeric {prefix.strip()} line to mutate")
                self.assertNotEqual(fingerprint_of(mutated), ruleset_fingerprint())

    def test_prose_only_edits_do_not_move_the_fingerprint(self):
        """Fixing a typo must stay free, or contributors learn to ignore the guard."""
        reworded = self.clone(
            mutate=lambda r: dataclasses.replace(
                r, title=r.title + " (clarified)", remediation=r.remediation + " Please."
            )
        )

        self.assertEqual(ruleset_fingerprint(reworded), current_release().fingerprint)

    def test_registration_order_does_not_move_the_fingerprint(self):
        shuffled = RuleRegistry()
        for rule in sorted(live_registry.all(), key=lambda r: r.id, reverse=True):
            shuffled.register(rule)

        self.assertEqual(ruleset_fingerprint(shuffled), current_release().fingerprint)


if __name__ == "__main__":
    unittest.main()
