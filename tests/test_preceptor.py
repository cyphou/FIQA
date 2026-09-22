"""Preceptorship loop behaviour.

The preceptor reviews the *assessment itself*, not the tenant: it is the guard
against a confident-looking report built on thin evidence.
"""

import unittest

from fabric_iq.errors import ReviewError
from fabric_iq.models import AssessmentRun
from fabric_iq.preceptor import (
    DIMENSIONS,
    DIMENSION_OWNER,
    MIN_PASS_SCORE,
    CoachingItem,
    PreceptorLoop,
    ReviewScorecard,
)
from fabric_iq.scoring import assess
from tests.helpers import minimal_inventory, ready_model


def healthy_run():
    return assess(minimal_inventory(semantic_models=[ready_model()]), run_id="run_ok")


class TestReviewScorecard(unittest.TestCase):
    def test_unknown_dimension_is_rejected(self):
        with self.assertRaises(ReviewError):
            ReviewScorecard().set("imagination", 5.0)

    def test_out_of_range_score_is_rejected(self):
        with self.assertRaises(ReviewError):
            ReviewScorecard().set(DIMENSIONS[0], 7.0)

    def test_average_of_empty_scorecard_is_zero(self):
        self.assertEqual(ReviewScorecard().average(), 0.0)

    def test_threshold_is_inclusive(self):
        card = ReviewScorecard()
        for dimension in DIMENSIONS:
            card.set(dimension, MIN_PASS_SCORE)
        self.assertTrue(card.passed())

    def test_just_below_threshold_fails(self):
        card = ReviewScorecard()
        for dimension in DIMENSIONS:
            card.set(dimension, MIN_PASS_SCORE)
        card.set(DIMENSIONS[0], MIN_PASS_SCORE - 0.5)
        self.assertFalse(card.passed())

    def test_weakest_identifies_the_lowest_dimension(self):
        card = ReviewScorecard()
        for dimension in DIMENSIONS:
            card.set(dimension, 5.0)
        card.set(DIMENSIONS[2], 1.0)
        self.assertEqual(card.weakest(), DIMENSIONS[2])


class TestCoachingItem(unittest.TestCase):
    def test_every_dimension_has_a_declared_owner(self):
        for dimension in DIMENSIONS:
            with self.subTest(dimension=dimension):
                self.assertTrue(DIMENSION_OWNER.get(dimension))

    def test_owner_is_resolved_from_the_dimension(self):
        item = CoachingItem(DIMENSIONS[0], 2.0, "issue", "where", "fix")
        self.assertEqual(item.owner, DIMENSION_OWNER[DIMENSIONS[0]])

    def test_unknown_dimension_is_rejected(self):
        with self.assertRaises(ReviewError):
            CoachingItem("nonsense", 2.0, "issue", "where", "fix")


class TestPreceptorLoop(unittest.TestCase):
    def test_empty_run_cannot_be_reviewed(self):
        with self.assertRaises(ReviewError):
            PreceptorLoop().review(AssessmentRun(run_id="empty", tenant_id="t"))

    def test_healthy_run_is_approved(self):
        report = PreceptorLoop().run(healthy_run())
        self.assertEqual(report.verdict, "approved")
        self.assertTrue(report.approved)
        self.assertEqual(len(report.cycles), 1)

    def test_coaching_is_only_emitted_below_threshold(self):
        report = PreceptorLoop().run(healthy_run())
        for item in report.open_items():
            self.assertLess(item.score, MIN_PASS_SCORE)

    def test_unfixable_run_escalates_without_burning_every_cycle(self):
        # The loop never repairs the run, so identical cycles must short-circuit.
        report = PreceptorLoop(threshold=5.01).run(healthy_run(), max_cycles=3)
        self.assertEqual(report.verdict, "escalated")
        self.assertEqual(len(report.cycles), 2, "should stop once a cycle repeats identically")

    def test_every_open_item_names_an_owner_and_an_action(self):
        report = PreceptorLoop(threshold=5.01).run(healthy_run())
        self.assertTrue(report.open_items())
        for item in report.open_items():
            self.assertTrue(item.owner)
            self.assertTrue(item.fix.strip())
            self.assertTrue(item.location.strip())

    def test_max_cycles_must_be_positive(self):
        with self.assertRaises(ReviewError):
            PreceptorLoop().run(healthy_run(), max_cycles=0)

    def test_all_six_dimensions_are_always_scored(self):
        card, _ = PreceptorLoop().review(healthy_run())
        self.assertEqual(set(card.scores), set(DIMENSIONS))

    def test_report_serialises(self):
        report = PreceptorLoop().run(healthy_run())
        payload = report.to_dict()
        self.assertEqual(payload["verdict"], "approved")
        self.assertIn("cycles", payload)

    def test_review_is_read_only_on_the_run(self):
        run = healthy_run()
        before = [(c.object_id, c.score) for c in run.scorecards]
        PreceptorLoop().run(run)
        self.assertEqual(before, [(c.object_id, c.score) for c in run.scorecards])


class TestPreceptorDetectsWeakAssessments(unittest.TestCase):
    def test_unreadable_model_lowers_the_coverage_review_score(self):
        strong = healthy_run()
        blind_model = ready_model(
            id="sm-blind", tables=None, columns=None, measures=None,
            ai_data_schema=None, ai_instructions=None, verified_answers=None,
            schema_retrieval_error="model not refreshed since deployment",
        )
        weak = assess(minimal_inventory(semantic_models=[blind_model]), run_id="run_weak")
        strong_card, _ = PreceptorLoop().review(strong)
        weak_card, coaching = PreceptorLoop().review(weak)
        self.assertLess(weak_card.scores["rule_coverage"], strong_card.scores["rule_coverage"])
        self.assertTrue(
            any(i.dimension == "rule_coverage" for i in coaching),
            "the preceptor must coach on an assessment it could not evidence",
        )


if __name__ == "__main__":
    unittest.main()
