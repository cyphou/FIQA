"""Trend and regression detection."""

import unittest
from dataclasses import replace

from fabric_iq.models import AssessmentRun, ObjectType, ReadinessStatus, Scorecard
from fabric_iq.trends import TrendClassification, compare_runs


def card(
    object_id: str,
    *,
    score: float = 80.0,
    coverage: float = 0.9,
    confidence: float = 0.8,
    object_type: ObjectType = ObjectType.SEMANTIC_MODEL,
) -> Scorecard:
    return Scorecard(
        object_id=object_id,
        object_name=object_id.upper(),
        object_type=object_type,
        score=score,
        raw_score=score,
        status=ReadinessStatus.READY,
        eligible=True,
        confidence=confidence,
        coverage=coverage,
        ruleset_version="2026.09.1",
    )


def run(run_id: str, *cards: Scorecard, ruleset_version: str = "2026.09.1") -> AssessmentRun:
    return AssessmentRun(
        run_id=run_id,
        tenant_id="tenant",
        ruleset_version=ruleset_version,
        scorecards=list(cards),
    )


class TestTrendComparison(unittest.TestCase):
    def test_score_drop_with_stable_coverage_is_quality_regression(self):
        report = compare_runs(
            run("baseline", card("model", score=90.0, coverage=0.95)),
            run("current", card("model", score=70.0, coverage=0.94)),
        )

        finding = report.findings[0]
        self.assertEqual(finding.classification, TrendClassification.QUALITY_REGRESSION)
        self.assertEqual(finding.score_delta, -20.0)
        self.assertIn("coverage remained stable", finding.detail)

    def test_score_drop_caused_by_coverage_loss_is_not_quality_regression(self):
        report = compare_runs(
            run("baseline", card("model", score=90.0, coverage=0.95)),
            run("current", card("model", score=70.0, coverage=0.55)),
        )

        finding = report.findings[0]
        self.assertEqual(finding.classification, TrendClassification.COVERAGE_LOSS)
        self.assertEqual(finding.score_delta, -20.0)
        self.assertEqual(finding.coverage_delta, -0.4)
        self.assertIn("collection incident", finding.detail)

    def test_ruleset_version_change_blocks_score_comparison(self):
        report = compare_runs(
            run("baseline", card("model", score=90.0), ruleset_version="2026.09.1"),
            run("current", card("model", score=70.0), ruleset_version="2026.10.1"),
        )

        self.assertTrue(report.ruleset_version_changed)
        self.assertEqual(report.findings[0].classification, TrendClassification.RULESET_CHANGED)

    def test_new_and_removed_objects_are_explicit(self):
        report = compare_runs(
            run("baseline", card("old")),
            run("current", card("new")),
        )

        by_id = {finding.object_id: finding for finding in report.findings}
        self.assertEqual(by_id["old"].classification, TrendClassification.REMOVED_OBJECT)
        self.assertEqual(by_id["new"].classification, TrendClassification.NEW_OBJECT)

    def test_findings_are_serializable(self):
        report = compare_runs(
            run("baseline", card("model")),
            run("current", replace(card("model"), score=86.0)),
        )

        payload = report.to_dict()
        self.assertEqual(payload["baseline_run_id"], "baseline")
        self.assertEqual(payload["current_run_id"], "current")
        self.assertEqual(payload["findings"][0]["classification"], "improved")

    def test_thresholds_must_be_non_negative(self):
        with self.assertRaises(ValueError):
            compare_runs(run("baseline"), run("current"), score_threshold=-1)
        with self.assertRaises(ValueError):
            compare_runs(run("baseline"), run("current"), coverage_threshold=-0.1)


if __name__ == "__main__":
    unittest.main()
