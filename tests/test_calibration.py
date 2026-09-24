"""Blinded practitioner calibration: blinding, sampling, agreement, enumeration.

Sprint 5.3 asks for a *mechanism*, and a mechanism whose guarantees are only
asserted in prose is not one. Four things are pinned here:

1. Blinding removes **every** verdict field, checked against the full forbidden
   set and against a real scorecard, not against two spot-checked keys.
2. Sampling is reproducible under a seed, bounded, and stratified.
3. The agreement maths reproduces a published reference example, and every
   degenerate case returns "undefined, and here is why" rather than a number.
4. Every disagreement is enumerated object by object; nothing is aggregated away.

There is also a gate on the thing this module must never become: the report
proposes nothing, and a full calibration round trip leaves the scoring weights
and thresholds untouched.
"""

import csv
import json
import os
import subprocess
import tempfile
import unittest

from fabric_iq.calibration import (
    BLINDED_FIELDS,
    CALIBRATION_ARTIFACTS,
    CALIBRATION_SINK_ROOT,
    DEFAULT_SEED,
    ORDINAL_RANK,
    ROADMAP_SAMPLE_BOUNDS,
    TOOL_RATER_ID,
    WORKSHEET_COLUMNS,
    CalibrationLabel,
    LabelSet,
    analyse,
    assert_blinded,
    build_worksheet,
    calibration_sinks,
    krippendorff_alpha,
    parse_label,
    read_labels,
    summarise,
    write_report,
    write_worksheet,
)
from fabric_iq.collectors import OfflineCollector
from fabric_iq.errors import ConfigurationError, ScoringError
from fabric_iq.models import (
    AssessmentRun,
    Dimension,
    Evidence,
    Finding,
    ObjectType,
    ReadinessStatus,
    RuleOutcome,
    RuleStatus,
    Scorecard,
    Severity,
)
from fabric_iq.scoring import assess
from tests.helpers import SAMPLE_TENANT

BAND_FIXTURES = (
    ("top", 92.0, ReadinessStatus.READY),
    ("mid", 55.0, ReadinessStatus.REMEDIATION_REQUIRED),
    ("low", 20.0, ReadinessStatus.NOT_READY),
)


def card(
    object_id,
    object_type=ObjectType.SEMANTIC_MODEL,
    score=80.0,
    status=ReadinessStatus.READY_WITH_CONDITIONS,
    findings=None,
    parent_id="",
    name=None,
):
    return Scorecard(
        object_id=object_id,
        object_name=name or f"Object {object_id}",
        object_type=object_type,
        parent_id=parent_id,
        score=score,
        raw_score=score,
        status=status,
        eligible=status is not ReadinessStatus.NOT_READY,
        confidence=0.8,
        coverage=0.9,
        dimension_scores={Dimension.SECURITY.value: score},
        findings=findings or [],
        ruleset_version="test",
    )


def finding(outcome, rule_id="SEM-001", severity=Severity.MINOR, object_id="o"):
    return Finding(
        rule_id=rule_id,
        title="A check",
        object_id=object_id,
        object_name="Object o",
        object_type=ObjectType.SEMANTIC_MODEL,
        dimension=Dimension.SECURITY,
        severity=severity,
        outcome=outcome,
    )


def synthetic_run(per_stratum=4, types=(ObjectType.SEMANTIC_MODEL, ObjectType.REPORT, ObjectType.DATA_AGENT)):
    """A run spanning every (type, band) combination, with no fact text."""
    run = AssessmentRun(run_id="run_synth", tenant_id="t", ruleset_version="test")
    for object_type in types:
        for band, score, status in BAND_FIXTURES:
            for index in range(per_stratum):
                run.scorecards.append(
                    card(
                        f"{object_type.value}-{band}-{index}",
                        object_type=object_type,
                        score=score,
                        status=status,
                    )
                )
    return run


def sample_run():
    collection = OfflineCollector(SAMPLE_TENANT).collect()
    return assess(collection.inventory, run_id="run_calibration_test")


def make_key(entries, run_id="run_k"):
    return {
        "run_id": run_id,
        "ruleset_version": "test",
        "entries": [
            {
                "label": label,
                "object_id": f"id-{label}",
                "object_name": f"Name {label}",
                "object_type": "semantic_model",
                "band": "mid",
                "tool_status": tool.value if tool is not CalibrationLabel.INSUFFICIENT_EVIDENCE else "not_evaluated",
                "tool_label": tool.value,
                "score": 60.0,
                "raw_score": 60.0,
                "eligible": True,
                "confidence": 0.5,
                "coverage": 0.6,
            }
            for label, tool in entries.items()
        ],
    }


def label_set(labeler_id, labels, rationales=None):
    return LabelSet(
        labeler_id=labeler_id,
        labels={unit: CalibrationLabel(value) for unit, value in labels.items()},
        rationales=dict(rationales or {}),
    )


# ── 1. blinding ──────────────────────────────────────────────────────────────


class BlindingTests(unittest.TestCase):
    def test_the_forbidden_set_names_every_field_the_brief_lists(self):
        # Non-vacuity: if BLINDED_FIELDS were trimmed, the assertions below would
        # keep passing while protecting less. Pin the required members explicitly.
        for required in (
            "score",
            "raw_score",
            "status",
            "eligible",
            "confidence",
            "coverage",
            "dimension_scores",
            "severity",
            "rule_id",
            "findings",
            "blocking_findings",
        ):
            with self.subTest(field=required):
                self.assertIn(required, BLINDED_FIELDS)

    def test_no_worksheet_column_is_a_verdict_field(self):
        self.assertEqual(set(WORKSHEET_COLUMNS) & BLINDED_FIELDS, set())

    def test_every_verdict_key_a_scorecard_publishes_is_absent_from_every_row(self):
        # Checked against the real serialisation rather than a remembered list, so a
        # new Scorecard field cannot quietly become a worksheet column.
        run = sample_run()
        worksheet = build_worksheet(run, size=13)
        published = set(run.scorecards[0].to_dict())
        neutral = {"object_type"}
        forbidden = published - neutral
        self.assertIn("score", forbidden)
        self.assertIn("status", forbidden)
        for row in worksheet.rows:
            with self.subTest(row=row.label):
                self.assertEqual(set(row.to_dict()) & forbidden, set())

    def test_no_row_reproduces_a_score_status_name_or_identifier(self):
        run = sample_run()
        worksheet = build_worksheet(run, size=13)
        by_label = {entry.label: entry for entry in worksheet.key}
        for row in worksheet.rows:
            entry = by_label[row.label]
            blob = "\n".join(row.to_dict().values())
            with self.subTest(row=row.label):
                self.assertNotIn(entry.object_name, blob)
                self.assertNotIn(entry.object_id, blob)
                self.assertNotIn(entry.tool_status, blob)
                self.assertNotIn(f"{entry.score:.1f}", blob)
                self.assertNotIn(f"{entry.score:.2f}", blob)
                self.assertNotIn(f"{entry.coverage:.4f}", blob)

    def test_status_vocabulary_never_appears_in_a_worksheet(self):
        # Word boundaries, restated independently of the module: "already" contains
        # "ready" and a substring test would fail on ordinary English instead of on
        # a leak.
        import re

        worksheet = build_worksheet(sample_run(), size=13)
        blob = "\n".join("\n".join(row.to_dict().values()) for row in worksheet.rows)
        vocabulary = [status.value for status in ReadinessStatus] + [
            RuleStatus.NOT_EVALUATED.value,
            RuleStatus.NOT_APPLICABLE.value,
        ]
        for word in vocabulary:
            pattern = re.compile(rf"(?<![A-Za-z0-9_]){word}(?![A-Za-z0-9_])", re.IGNORECASE)
            with self.subTest(word=word):
                self.assertIsNone(pattern.search(blob), f"{word!r} leaked into a worksheet")

    def test_a_leaked_status_word_is_caught_by_the_gate(self):
        # Mutation proof: the gate must fail on a planted leak, otherwise the
        # assertions above only prove that today's rules happen to be clean.
        worksheet = build_worksheet(synthetic_run(per_stratum=2), size=6)
        leaked = worksheet.rows[0].__class__(
            **{**worksheet.rows[0].to_dict(), "observed_facts": "the object is not_ready"}
        )
        worksheet.rows[0] = leaked
        with self.assertRaises(ScoringError):
            assert_blinded(worksheet)

    def test_a_leaked_object_name_is_caught_by_the_gate(self):
        worksheet = build_worksheet(synthetic_run(per_stratum=2), size=6)
        name = worksheet.pseudonyms[worksheet.rows[0].label]["object_name"]
        worksheet.rows[0] = worksheet.rows[0].__class__(
            **{**worksheet.rows[0].to_dict(), "rationale": f"seen in {name}"}
        )
        with self.assertRaises(ScoringError):
            assert_blinded(worksheet)

    def test_a_leaked_score_is_caught_by_the_gate(self):
        worksheet = build_worksheet(synthetic_run(per_stratum=2), size=6)
        entry = {e.label: e for e in worksheet.key}[worksheet.rows[0].label]
        worksheet.rows[0] = worksheet.rows[0].__class__(
            **{**worksheet.rows[0].to_dict(), "observed_facts": f"weight {entry.score:.2f}"}
        )
        with self.assertRaises(ScoringError):
            assert_blinded(worksheet)

    def test_a_fact_quoting_another_objects_score_is_dropped(self):
        # assess() enriches a report with its model's score, so a rule can
        # legitimately publish the engine's verdict on a neighbour. That is the
        # verdict one hop away and must not reach a labeler.
        quoting = finding(
            RuleOutcome.failed(
                "source semantic model scores 11/100", observed={"model_score": 11.1}
            ),
            rule_id="REP-001",
        )
        plain = finding(
            RuleOutcome.passed("9/9 visuals carry alt text", observed={"visuals": 9}),
            rule_id="REP-002",
        )
        run = AssessmentRun(run_id="r", tenant_id="t", ruleset_version="test")
        run.scorecards.append(card("only", findings=[quoting, plain]))
        worksheet = build_worksheet(run, size=1)
        facts = worksheet.rows[0].observed_facts
        self.assertIn("9/9 visuals carry alt text", facts)
        self.assertNotIn("11/100", facts)
        self.assertNotIn("model_score", facts)

    def test_observable_facts_and_evidence_survive_blinding(self):
        # Blinding that also removed the facts would produce an uninformed label,
        # which is a different way of wasting the exercise.
        outcome = RuleOutcome.partial(
            0.5,
            "3/6 visible measures described",
            observed={"undescribed": ["Margin"]},
            evidence=[Evidence(source="scanner_api", reference="model.measures")],
        )
        run = AssessmentRun(run_id="r", tenant_id="t", ruleset_version="test")
        run.scorecards.append(card("only", findings=[finding(outcome)]))
        row = build_worksheet(run, size=1).rows[0]
        self.assertIn("3/6 visible measures described", row.observed_facts)
        self.assertIn("undescribed=", row.observed_facts)
        self.assertIn("scanner_api:model.measures", row.evidence_references)

    def test_unobserved_evidence_is_declared_without_naming_the_rule(self):
        outcome = RuleOutcome.not_evaluated(
            "missing evidence: rls_roles", observed={"missing_keys": ["rls_roles"]}
        )
        run = AssessmentRun(run_id="r", tenant_id="t", ruleset_version="test")
        run.scorecards.append(card("only", findings=[finding(outcome, rule_id="SEM-015")]))
        row = build_worksheet(run, size=1).rows[0]
        self.assertIn("not observed: rls_roles", row.observed_facts)
        self.assertNotIn("SEM-015", row.observed_facts)

    def test_not_applicable_rules_are_omitted_entirely(self):
        run = AssessmentRun(run_id="r", tenant_id="t", ruleset_version="test")
        run.scorecards.append(
            card(
                "only",
                findings=[finding(RuleOutcome.not_applicable("no date logic in the model"))],
            )
        )
        row = build_worksheet(run, size=1).rows[0]
        self.assertNotIn("no date logic", row.observed_facts)

    def test_names_are_pseudonymised_and_the_mapping_lives_only_in_the_key(self):
        worksheet = build_worksheet(sample_run(), size=13)
        for row in worksheet.rows:
            with self.subTest(row=row.label):
                self.assertRegex(row.label, r"^[A-Z]{2}-\d{2}$")
        names = {entry.object_name for entry in worksheet.key}
        self.assertTrue(names)
        self.assertTrue(all(name for name in names))

    def test_row_order_does_not_follow_the_tool_ranking(self):
        # A worksheet sorted by score hands over the ranking, which is most of the
        # verdict. The shuffle must break both the ascending and descending order.
        worksheet = build_worksheet(synthetic_run(per_stratum=4), size=24)
        by_label = {entry.label: entry for entry in worksheet.key}
        scores = [by_label[row.label].score for row in worksheet.rows]
        self.assertNotEqual(scores, sorted(scores))
        self.assertNotEqual(scores, sorted(scores, reverse=True))


# ── 2. sampling ──────────────────────────────────────────────────────────────


class SamplingTests(unittest.TestCase):
    def test_a_fixed_seed_reproduces_the_same_sample_in_the_same_order(self):
        run = synthetic_run()
        first = build_worksheet(run, size=24, seed=DEFAULT_SEED)
        second = build_worksheet(run, size=24, seed=DEFAULT_SEED)
        self.assertEqual(
            [row.label for row in first.rows], [row.label for row in second.rows]
        )
        self.assertEqual(
            [entry.object_id for entry in first.key], [entry.object_id for entry in second.key]
        )

    def test_a_different_seed_draws_a_different_sample(self):
        run = synthetic_run()
        first = build_worksheet(run, size=24, seed=1)
        second = build_worksheet(run, size=24, seed=2)
        self.assertNotEqual(
            [entry.object_id for entry in first.key],
            [entry.object_id for entry in second.key],
        )

    def test_the_sample_respects_the_requested_bound(self):
        run = synthetic_run()
        for size in (20, 24, 30):
            with self.subTest(size=size):
                self.assertEqual(len(build_worksheet(run, size=size).rows), size)

    def test_the_default_size_sits_inside_the_roadmap_band(self):
        low, high = ROADMAP_SAMPLE_BOUNDS
        from fabric_iq.calibration import DEFAULT_SAMPLE_SIZE

        self.assertLessEqual(low, DEFAULT_SAMPLE_SIZE)
        self.assertLessEqual(DEFAULT_SAMPLE_SIZE, high)

    def test_the_sample_spans_object_types_and_quality_bands(self):
        # A sample that is all one type, or all healthy, is indistinguishable from
        # cherry-picking and says nothing about whether the thresholds hold.
        worksheet = build_worksheet(synthetic_run(), size=9)
        strata = worksheet.strata
        self.assertEqual(len(strata), 9)
        self.assertEqual(sum(strata.values()), 9)
        types = {stratum.split("/")[0] for stratum in strata}
        bands = {stratum.split("/")[1] for stratum in strata}
        self.assertEqual(len(types), 3)
        self.assertEqual(bands, {"top", "mid", "low"})

    def test_one_dominant_stratum_cannot_swallow_the_sample(self):
        run = AssessmentRun(run_id="r", tenant_id="t", ruleset_version="test")
        for index in range(40):
            run.scorecards.append(card(f"bulk-{index}", score=92.0, status=ReadinessStatus.READY))
        run.scorecards.append(
            card("rare", object_type=ObjectType.REPORT, score=10.0, status=ReadinessStatus.NOT_READY)
        )
        worksheet = build_worksheet(run, size=20)
        self.assertIn("report/low", worksheet.strata)

    def test_the_quality_band_never_reaches_a_worksheet_row(self):
        worksheet = build_worksheet(synthetic_run(), size=9)
        blob = "\n".join("\n".join(row.to_dict().values()) for row in worksheet.rows)
        for band in ("top", "mid", "low"):
            with self.subTest(band=band):
                self.assertNotIn(f"/{band}", blob)
        self.assertTrue(all(entry.band for entry in worksheet.key))

    def test_a_pool_smaller_than_the_request_is_noted_never_padded(self):
        worksheet = build_worksheet(synthetic_run(per_stratum=1), size=24)
        self.assertEqual(len(worksheet.rows), 9)
        self.assertEqual(len({row.label for row in worksheet.rows}), 9)
        self.assertTrue(any("outside the roadmap" in note for note in worksheet.notes))

    def test_a_size_below_one_is_refused(self):
        with self.assertRaises(ScoringError):
            build_worksheet(synthetic_run(), size=0)

    def test_a_run_with_no_scorecards_is_refused(self):
        with self.assertRaises(ScoringError):
            build_worksheet(AssessmentRun(run_id="r", tenant_id="t"), size=5)

    def test_a_sampled_child_names_its_parent_by_pseudonym(self):
        run = AssessmentRun(run_id="r", tenant_id="t", ruleset_version="test")
        run.scorecards.append(card("ws-1", object_type=ObjectType.WORKSPACE))
        run.scorecards.append(card("sm-1", parent_id="ws-1"))
        worksheet = build_worksheet(run, size=2)
        rows = {row.label: row for row in worksheet.rows}
        child = next(row for row in rows.values() if row.object_type == "semantic_model")
        self.assertTrue(child.parent_label.startswith("WS-"))


# ── 3. agreement maths ───────────────────────────────────────────────────────


class AlphaTests(unittest.TestCase):
    #: Krippendorff's canonical worked example (three observers, fifteen units,
    #: many missing values). Published values: nominal 0.691, ordinal 0.807.
    REFERENCE = {
        "2": [2, 2],
        "3": [1, 1],
        "4": [3, 3],
        "5": [3, 3, 4],
        "6": [4, 4, 4],
        "7": [1, 3],
        "8": [2, 2],
        "9": [1, 1],
        "10": [1, 1],
        "11": [3, 3],
        "12": [3, 3],
        "14": [3, 4],
    }

    def test_nominal_alpha_reproduces_the_published_reference(self):
        alpha, units, reason = krippendorff_alpha(self.REFERENCE, metric="nominal")
        self.assertEqual(reason, "")
        self.assertEqual(units, 12)
        self.assertAlmostEqual(alpha, 0.691, places=3)

    def test_ordinal_alpha_reproduces_the_published_reference(self):
        alpha, _units, reason = krippendorff_alpha(
            self.REFERENCE, metric="ordinal", category_order=[1, 2, 3, 4]
        )
        self.assertEqual(reason, "")
        self.assertAlmostEqual(alpha, 0.807, places=3)

    def test_perfect_agreement_across_several_classes_is_one(self):
        units = {"a": ["x", "x"], "b": ["y", "y"], "c": ["z", "z"]}
        alpha, _units, reason = krippendorff_alpha(units, metric="nominal")
        self.assertEqual(reason, "")
        self.assertAlmostEqual(alpha, 1.0)

    def test_systematic_disagreement_is_reported_negative_not_clamped(self):
        units = {"a": ["x", "y"], "b": ["y", "x"], "c": ["x", "y"], "d": ["y", "x"]}
        alpha, _units, reason = krippendorff_alpha(units, metric="nominal")
        self.assertEqual(reason, "")
        self.assertLess(alpha, 0.0)

    def test_the_ordinal_metric_punishes_a_distant_disagreement_harder(self):
        ladder = [0, 1, 2, 3]
        near = {"a": [0, 1], "b": [2, 2], "c": [3, 3], "d": [1, 1], "e": [2, 2]}
        far = {"a": [0, 3], "b": [2, 2], "c": [3, 3], "d": [1, 1], "e": [2, 2]}
        near_alpha, _n, _r = krippendorff_alpha(near, metric="ordinal", category_order=ladder)
        far_alpha, _n2, _r2 = krippendorff_alpha(far, metric="ordinal", category_order=ladder)
        self.assertGreater(near_alpha, far_alpha)

    def test_a_one_class_sample_is_undefined_not_perfect(self):
        # The single most flattering lie available: two labelers who both wrote
        # "not ready" on every row agree 100% of the time and have demonstrated
        # nothing. Reporting 1.0 here would launder that into a credential.
        units = {"a": ["not_ready", "not_ready"], "b": ["not_ready", "not_ready"]}
        alpha, _units, reason = krippendorff_alpha(units, metric="nominal")
        self.assertIsNone(alpha)
        self.assertIn("unmeasurable rather than perfect", reason)

    def test_nothing_comparable_is_undefined(self):
        alpha, units, reason = krippendorff_alpha({"a": ["x"], "b": ["y"]}, metric="nominal")
        self.assertIsNone(alpha)
        self.assertEqual(units, 0)
        self.assertIn("nothing is comparable", reason)

    def test_an_unknown_metric_is_refused(self):
        with self.assertRaises(ConfigurationError):
            krippendorff_alpha({"a": ["x", "x"]}, metric="cohen")


# ── 4. NOT_EVALUATED / insufficient evidence ─────────────────────────────────


class InsufficientEvidenceTests(unittest.TestCase):
    def test_insufficient_evidence_has_no_rung_on_the_ladder(self):
        self.assertNotIn(CalibrationLabel.INSUFFICIENT_EVIDENCE, ORDINAL_RANK)
        self.assertEqual(ORDINAL_RANK[CalibrationLabel.NOT_READY], 0)
        self.assertEqual(len(ORDINAL_RANK), 4)

    def test_it_is_excluded_from_the_ordinal_comparison_not_ranked_worst(self):
        key = make_key(
            {
                "SM-01": CalibrationLabel.READY,
                "SM-02": CalibrationLabel.READY,
                "SM-03": CalibrationLabel.NOT_READY,
            }
        )
        with_gap = analyse(
            key,
            [
                label_set("a", {"SM-01": "ready", "SM-02": "insufficient_evidence", "SM-03": "not_ready"}),
                label_set("b", {"SM-01": "ready", "SM-02": "not_ready", "SM-03": "not_ready"}),
            ],
        )
        # SM-02 carries only one ladder label, so it cannot enter a pairwise
        # ordinal comparison at all. It must not be scored as a 3-step gap.
        self.assertEqual(with_gap.inter_rater.units_compared, 2)
        involving_a = [
            d
            for d in with_gap.disagreements
            if d.unit == "SM-02" and "a" in (d.left_rater, d.right_rater)
        ]
        self.assertEqual(len(involving_a), 2)
        self.assertTrue(all(d.ordinal_distance is None for d in involving_a))
        self.assertTrue(all(d.kind == "coverage" for d in involving_a))

    def test_a_blind_spot_divergence_is_classified_as_coverage_not_readiness(self):
        key = make_key({"SM-01": CalibrationLabel.READY})
        report = analyse(
            key,
            [
                label_set("a", {"SM-01": "insufficient_evidence"}),
                label_set("b", {"SM-01": "ready"}),
            ],
        )
        kinds = {d.kind for d in report.disagreements}
        self.assertEqual(kinds, {"coverage"})
        self.assertEqual(report.readiness_disagreements, [])
        self.assertEqual(len(report.coverage_disagreements), 2)

    def test_agreement_about_where_the_blind_spots_are_is_measured_separately(self):
        key = make_key(
            {
                "SM-01": CalibrationLabel.READY,
                "SM-02": CalibrationLabel.READY,
                "SM-03": CalibrationLabel.READY,
            }
        )
        report = analyse(
            key,
            [
                label_set(
                    "a",
                    {"SM-01": "insufficient_evidence", "SM-02": "ready", "SM-03": "not_ready"},
                ),
                label_set(
                    "b",
                    {"SM-01": "insufficient_evidence", "SM-02": "ready", "SM-03": "ready"},
                ),
            ],
        )
        self.assertEqual(report.blind_spot_agreement.units_compared, 3)
        self.assertAlmostEqual(report.blind_spot_agreement.value, 1.0)
        self.assertEqual(report.coverage_units, ["SM-01"])

    def test_a_tool_not_evaluated_verdict_is_held_out_of_tool_agreement(self):
        key = make_key(
            {
                "SM-01": CalibrationLabel.INSUFFICIENT_EVIDENCE,
                "SM-02": CalibrationLabel.READY,
                "SM-03": CalibrationLabel.NOT_READY,
            }
        )
        report = analyse(
            key,
            [
                label_set("a", {"SM-01": "ready", "SM-02": "ready", "SM-03": "not_ready"}),
                label_set("b", {"SM-01": "ready", "SM-02": "ready", "SM-03": "not_ready"}),
            ],
        )
        self.assertEqual(report.tool_agreement["a"].units_compared, 2)
        coverage = [d for d in report.disagreements if d.unit == "SM-01"]
        self.assertTrue(coverage)
        self.assertTrue(all(d.kind == "coverage" for d in coverage))


# ── 5. degenerate labelling ──────────────────────────────────────────────────


class DegenerateCaseTests(unittest.TestCase):
    def test_one_labeler_yields_undefined_inter_rater_agreement(self):
        key = make_key({"SM-01": CalibrationLabel.READY, "SM-02": CalibrationLabel.NOT_READY})
        report = analyse(key, [label_set("solo", {"SM-01": "ready", "SM-02": "not_ready"})])
        self.assertIsNone(report.inter_rater.value)
        self.assertIn("at least two independent labelers", report.inter_rater.undefined_reason)
        self.assertEqual(report.inter_rater.raters, 1)
        # The tool comparison still runs, and is meaningless on its own — which is
        # why the undefined reason above has to be published beside it.
        self.assertIsNotNone(report.tool_agreement["solo"])

    def test_a_labeler_who_marked_everything_the_same_is_warned(self):
        key = make_key(
            {
                "SM-01": CalibrationLabel.READY,
                "SM-02": CalibrationLabel.NOT_READY,
                "SM-03": CalibrationLabel.READY,
            }
        )
        report = analyse(
            key,
            [
                label_set("flat", {"SM-01": "ready", "SM-02": "ready", "SM-03": "ready"}),
                label_set("varied", {"SM-01": "ready", "SM-02": "not_ready", "SM-03": "ready"}),
            ],
        )
        self.assertTrue(
            any("used a single label" in warning for warning in report.inter_rater.warnings)
        )

    def test_both_labelers_flat_on_one_class_is_undefined_not_perfect(self):
        key = make_key({"SM-01": CalibrationLabel.READY, "SM-02": CalibrationLabel.READY})
        report = analyse(
            key,
            [
                label_set("a", {"SM-01": "ready", "SM-02": "ready"}),
                label_set("b", {"SM-01": "ready", "SM-02": "ready"}),
            ],
        )
        self.assertIsNone(report.inter_rater.value)
        self.assertIn("unmeasurable", report.inter_rater.undefined_reason)
        self.assertEqual(report.inter_rater.percent_agreement, 1.0)

    def test_partial_worksheets_are_reported_not_imputed(self):
        key = make_key(
            {
                "SM-01": CalibrationLabel.READY,
                "SM-02": CalibrationLabel.READY,
                "SM-03": CalibrationLabel.NOT_READY,
            }
        )
        report = analyse(
            key,
            [
                label_set("a", {"SM-01": "ready", "SM-03": "not_ready"}),
                label_set("b", {"SM-01": "not_ready", "SM-02": "ready", "SM-03": "not_ready"}),
            ],
        )
        self.assertEqual(report.inter_rater.units_compared, 2)
        self.assertTrue(any("unlabelled" in warning for warning in report.inter_rater.warnings))

    def test_a_row_nobody_labelled_is_listed(self):
        key = make_key({"SM-01": CalibrationLabel.READY, "SM-02": CalibrationLabel.READY})
        report = analyse(
            key,
            [label_set("a", {"SM-01": "ready"}), label_set("b", {"SM-01": "ready"})],
        )
        self.assertEqual(report.unlabelled_units, ["SM-02"])

    def test_a_unit_outside_the_key_is_recorded_as_a_problem(self):
        key = make_key({"SM-01": CalibrationLabel.READY})
        report = analyse(
            key,
            [
                label_set("a", {"SM-01": "ready", "ZZ-99": "ready"}),
                label_set("b", {"SM-01": "ready"}),
            ],
        )
        self.assertTrue(any("ZZ-99" in problem for problem in report.problems))

    def test_two_label_sets_with_the_same_id_are_refused(self):
        key = make_key({"SM-01": CalibrationLabel.READY})
        with self.assertRaises(ConfigurationError):
            analyse(key, [label_set("a", {"SM-01": "ready"}), label_set("a", {"SM-01": "not_ready"})])

    def test_an_empty_key_is_refused(self):
        with self.assertRaises(ConfigurationError):
            analyse({"run_id": "r", "entries": []}, [label_set("a", {})])


class LabelParsingTests(unittest.TestCase):
    def test_practitioner_spellings_are_accepted(self):
        for raw, expected in (
            ("Ready", CalibrationLabel.READY),
            ("ready with conditions", CalibrationLabel.READY_WITH_CONDITIONS),
            ("Remediation Required", CalibrationLabel.REMEDIATION_REQUIRED),
            ("not-ready", CalibrationLabel.NOT_READY),
            ("insufficient evidence", CalibrationLabel.INSUFFICIENT_EVIDENCE),
        ):
            with self.subTest(raw=raw):
                self.assertIs(parse_label(raw), expected)

    def test_a_blank_cell_is_a_missing_label_not_an_error(self):
        self.assertIsNone(parse_label("  "))

    def test_an_unknown_label_is_refused_rather_than_dropped(self):
        with self.assertRaises(ConfigurationError):
            parse_label("probably fine")


class LabelFileTests(unittest.TestCase):
    def write_worksheet_csv(self, folder, rows):
        path = os.path.join(folder, "labeler.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(WORKSHEET_COLUMNS))
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in WORKSHEET_COLUMNS})
        return path

    def test_blank_and_invalid_cells_are_both_recorded(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = self.write_worksheet_csv(
                tmp,
                [
                    {"label": "SM-01", "readiness_label": "ready", "rationale": "documented"},
                    {"label": "SM-02", "readiness_label": ""},
                    {"label": "SM-03", "readiness_label": "looks alright"},
                ],
            )
            labels = read_labels(path, "kim")
            self.assertEqual(set(labels.labels), {"SM-01"})
            self.assertEqual(labels.rationales["SM-01"], "documented")
            self.assertTrue(any("SM-02" in problem for problem in labels.problems))
            self.assertTrue(any("SM-03" in problem for problem in labels.problems))

    def test_the_file_stem_becomes_the_labeler_id_when_none_is_given(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = self.write_worksheet_csv(tmp, [{"label": "SM-01", "readiness_label": "ready"}])
            self.assertEqual(read_labels(path).labeler_id, "labeler")

    def test_a_csv_that_is_not_a_worksheet_is_refused(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = os.path.join(tmp, "other.csv")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write("a,b\n1,2\n")
            with self.assertRaises(ConfigurationError):
                read_labels(path)


# ── 6. every disagreement, enumerated ────────────────────────────────────────


class DisagreementEnumerationTests(unittest.TestCase):
    def report(self):
        key = make_key(
            {
                "SM-01": CalibrationLabel.READY,
                "SM-02": CalibrationLabel.NOT_READY,
                "SM-03": CalibrationLabel.REMEDIATION_REQUIRED,
            }
        )
        return analyse(
            key,
            [
                label_set(
                    "ann",
                    {"SM-01": "ready", "SM-02": "remediation_required", "SM-03": "remediation_required"},
                    {"SM-02": "the refresh history is the problem"},
                ),
                label_set(
                    "bob",
                    {"SM-01": "ready", "SM-02": "not_ready", "SM-03": "ready"},
                ),
            ],
        )

    def test_every_pair_that_diverged_is_listed_object_by_object(self):
        # The roadmap requires "agreement and every disagreement". An aggregate that
        # hides which object diverged fails that outright: the diverging row is the
        # only thing that could ever justify a change to the maths.
        found = {
            (item.unit, item.left_rater, item.right_rater) for item in self.report().disagreements
        }
        self.assertEqual(
            found,
            {
                ("SM-02", "ann", "bob"),
                ("SM-02", "ann", TOOL_RATER_ID),
                ("SM-03", "ann", "bob"),
                ("SM-03", "bob", TOOL_RATER_ID),
            },
        )

    def test_an_object_everybody_agreed_on_produces_no_row(self):
        self.assertNotIn("SM-01", {item.unit for item in self.report().disagreements})

    def test_the_ordinal_distance_is_recorded_for_each_divergence(self):
        distances = {
            (item.unit, item.left_rater, item.right_rater): item.ordinal_distance
            for item in self.report().disagreements
        }
        self.assertEqual(distances[("SM-02", "ann", "bob")], 1)
        self.assertEqual(distances[("SM-03", "bob", TOOL_RATER_ID)], 2)

    def test_the_rationale_travels_with_the_disagreement(self):
        item = next(
            d
            for d in self.report().disagreements
            if d.unit == "SM-02" and d.right_rater == "bob"
        )
        self.assertEqual(item.left_rationale, "the refresh history is the problem")

    def test_the_csv_carries_one_row_per_disagreement(self):
        report = self.report()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = report.disagreements_to_csv(os.path.join(tmp, "d.csv"))
            with open(path, encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), len(report.disagreements))
        self.assertEqual({row["unit"] for row in rows}, {"SM-02", "SM-03"})

    def test_the_serialised_report_carries_the_rows_not_only_the_count(self):
        payload = json.loads(self.report().to_json())
        self.assertEqual(payload["disagreement_counts"]["total"], 4)
        self.assertEqual(len(payload["disagreements"]), 4)

    def test_inter_rater_agreement_is_serialised_before_tool_agreement(self):
        # Ordering is the argument: if the practitioners do not agree with each
        # other, their disagreement with the tool measures the exercise, not the
        # engine. A reader who meets the tool number first draws the wrong
        # conclusion, so the key order is part of the contract.
        keys = list(self.report().to_dict())
        self.assertLess(keys.index("inter_rater_agreement"), keys.index("tool_agreement"))

    def test_the_console_summary_names_every_disagreeing_object(self):
        report = self.report()
        text = summarise(report)
        for item in report.disagreements:
            with self.subTest(unit=item.unit):
                self.assertIn(item.unit, text)


# ── 7. the line this must never cross ────────────────────────────────────────


class NoProposalTests(unittest.TestCase):
    def test_the_report_proposes_nothing(self):
        key = make_key({"SM-01": CalibrationLabel.READY, "SM-02": CalibrationLabel.NOT_READY})
        report = analyse(
            key,
            [
                label_set("a", {"SM-01": "not_ready", "SM-02": "ready"}),
                label_set("b", {"SM-01": "not_ready", "SM-02": "ready"}),
            ],
        )
        self.assertEqual(list(report.proposals), [])
        payload = json.loads(report.to_json())
        self.assertEqual(payload["proposals"], [])
        self.assertIn("proposes no weight", payload["proposals_note"])

    def test_a_full_round_trip_leaves_the_scoring_maths_untouched(self):
        # The guarantee that matters more than the wording above: calibration reads
        # the engine, it never writes to it. Total disagreement must move nothing.
        from fabric_iq import scoring
        from fabric_iq.models import SEVERITY_SCORE_CAP

        before = (
            json.dumps(
                {
                    object_type.value: {d.value: w for d, w in weights.items()}
                    for object_type, weights in scoring.DIMENSION_WEIGHTS.items()
                },
                sort_keys=True,
            ),
            [(threshold, status.value) for threshold, status in scoring.STATUS_THRESHOLDS],
            scoring.MIN_COVERAGE_TO_PUBLISH,
            dict(scoring.WORKSPACE_ROLLUP),
            dict(scoring.TENANT_ROLLUP),
            {severity.value: cap for severity, cap in SEVERITY_SCORE_CAP.items()},
        )

        run = sample_run()
        worksheet = build_worksheet(run, size=13)
        key = worksheet.key_to_dict()
        flipped = {
            entry.label: (
                "ready" if entry.tool_label != CalibrationLabel.READY.value else "not_ready"
            )
            for entry in worksheet.key
        }
        analyse(key, [label_set("a", flipped), label_set("b", flipped)])

        after = (
            json.dumps(
                {
                    object_type.value: {d.value: w for d, w in weights.items()}
                    for object_type, weights in scoring.DIMENSION_WEIGHTS.items()
                },
                sort_keys=True,
            ),
            [(threshold, status.value) for threshold, status in scoring.STATUS_THRESHOLDS],
            scoring.MIN_COVERAGE_TO_PUBLISH,
            dict(scoring.WORKSPACE_ROLLUP),
            dict(scoring.TENANT_ROLLUP),
            {severity.value: cap for severity, cap in SEVERITY_SCORE_CAP.items()},
        )
        self.assertEqual(before, after)


# ── 8. the evidence sink ─────────────────────────────────────────────────────


def _git_available():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return False
    return True


class SinkTests(unittest.TestCase):
    def test_the_writers_emit_only_the_enumerated_artifacts(self):
        # Closes the loop with calibration_sinks(): a new output file that skipped
        # the enumeration would also skip the ignore-rule gate built on it.
        known = tuple(suffix for suffix, _why in CALIBRATION_ARTIFACTS)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            worksheet = build_worksheet(synthetic_run(per_stratum=2), size=6)
            write_worksheet(worksheet, tmp)
            report = analyse(
                worksheet.key_to_dict(),
                [
                    label_set("a", {worksheet.rows[0].label: "ready"}),
                    label_set("b", {worksheet.rows[0].label: "not_ready"}),
                ],
            )
            write_report(report, tmp)
            written = sorted(os.listdir(tmp))
        self.assertEqual(len(written), len(known))
        for name in written:
            with self.subTest(name=name):
                self.assertTrue(name.endswith(known), f"{name} is not an enumerated sink")

    def test_the_default_destination_sits_under_a_known_sink_root(self):
        from scripts.check_evidence_sinks import SINK_ROOTS

        self.assertIn(CALIBRATION_SINK_ROOT.split("/")[0], SINK_ROOTS)

    @unittest.skipUnless(_git_available(), "git is required to resolve ignore rules")
    def test_every_calibration_destination_matches_a_committed_ignore_rule(self):
        from scripts.check_evidence_sinks import REPO_ROOT, check_sinks

        problems = check_sinks(REPO_ROOT, calibration_sinks())
        self.assertEqual(problems, [], f"unprotected calibration destinations: {problems}")

    def test_the_key_declares_that_it_is_never_handed_over(self):
        worksheet = build_worksheet(synthetic_run(per_stratum=2), size=6)
        payload = worksheet.key_to_dict()
        self.assertIn("Never hand this file to a labeler", payload["privacy"])
        self.assertEqual(payload["sampling"]["seed"], DEFAULT_SEED)


# ── 9. CLI ───────────────────────────────────────────────────────────────────


class CliTests(unittest.TestCase):
    def test_calibration_is_opt_in(self):
        import assess as cli

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = os.path.join(tmp, "out")
            code = cli.main(
                ["--inventory", SAMPLE_TENANT, "--out", out, "--no-html", "--quiet", "--run-id", "r1"]
            )
            self.assertEqual(code, 0)
            written = os.listdir(out)
        self.assertFalse([name for name in written if "calibration" in name])

    def test_the_calibration_flag_writes_the_worksheet_the_instructions_and_the_key(self):
        import assess as cli

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = os.path.join(tmp, "out")
            folder = os.path.join(tmp, "calibration")
            code = cli.main(
                [
                    "--inventory", SAMPLE_TENANT, "--out", out, "--no-html", "--quiet",
                    "--run-id", "r2", "--calibration", folder, "--calibration-size", "8",
                ]
            )
            self.assertEqual(code, 0)
            written = sorted(os.listdir(folder))
        self.assertEqual(
            written,
            [
                "r2_calibration_instructions.md",
                "r2_calibration_key.json",
                "r2_calibration_worksheet.csv",
            ],
        )

    def test_the_analysis_mode_runs_without_an_inventory(self):
        import assess as cli

        run = sample_run()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            worksheet = build_worksheet(run, size=6)
            paths = write_worksheet(worksheet, tmp)
            filled = []
            for name, choice in (("ann", "ready"), ("bob", "not_ready")):
                path = os.path.join(tmp, f"{name}.csv")
                with open(paths["worksheet"], encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                with open(path, "w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(WORKSHEET_COLUMNS))
                    writer.writeheader()
                    for row in rows:
                        row["readiness_label"] = choice
                        writer.writerow(row)
                filled.append(f"{name}={path}")
            code = cli.main(
                ["--calibration-analyse", paths["key"], "--calibration-labels", *filled, "--quiet"]
            )
            self.assertEqual(code, 0)
            self.assertTrue(
                os.path.exists(os.path.join(tmp, f"{run.run_id}_calibration_agreement.json"))
            )

    def test_labels_without_the_analysis_flag_are_refused(self):
        import assess as cli

        self.assertEqual(cli.main(["--calibration-labels", "a.csv"]), 1)

    def test_the_analysis_flag_without_labels_is_refused(self):
        import assess as cli

        self.assertEqual(cli.main(["--calibration-analyse", "nowhere.json"]), 1)


if __name__ == "__main__":
    unittest.main()
