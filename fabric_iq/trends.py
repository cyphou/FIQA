"""Trend and regression analysis across assessment runs.

Static readiness says whether one run is healthy. Trend analysis compares two
runs without confusing a quality regression with a collection/coverage incident.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from fabric_iq.models import AssessmentRun, Scorecard


class TrendClassification(str, Enum):
    """How an assessed object changed between two runs."""

    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    QUALITY_REGRESSION = "quality_regression"
    COVERAGE_LOSS = "coverage_loss"
    COVERAGE_GAIN = "coverage_gain"
    NEW_OBJECT = "new_object"
    REMOVED_OBJECT = "removed_object"
    RULESET_CHANGED = "ruleset_changed"


@dataclass(frozen=True)
class TrendFinding:
    """One object-level comparison between a baseline and current run."""

    object_id: str
    object_name: str
    object_type: str
    baseline_run_id: str
    current_run_id: str
    classification: TrendClassification
    score_delta: float = 0.0
    confidence_delta: float = 0.0
    coverage_delta: float = 0.0
    baseline_score: float | None = None
    current_score: float | None = None
    baseline_coverage: float | None = None
    current_coverage: float | None = None
    baseline_confidence: float | None = None
    current_confidence: float | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "object_id": self.object_id,
            "object_name": self.object_name,
            "object_type": self.object_type,
            "baseline_run_id": self.baseline_run_id,
            "current_run_id": self.current_run_id,
            "classification": self.classification.value,
            "score_delta": round(self.score_delta, 2),
            "confidence_delta": round(self.confidence_delta, 4),
            "coverage_delta": round(self.coverage_delta, 4),
            "baseline_score": self.baseline_score,
            "current_score": self.current_score,
            "baseline_coverage": self.baseline_coverage,
            "current_coverage": self.current_coverage,
            "baseline_confidence": self.baseline_confidence,
            "current_confidence": self.current_confidence,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class TrendReport:
    """Comparison report for two assessment runs."""

    baseline_run_id: str
    current_run_id: str
    ruleset_version_changed: bool
    findings: list[TrendFinding]

    def by_classification(self, classification: TrendClassification) -> list[TrendFinding]:
        return [f for f in self.findings if f.classification is classification]

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline_run_id": self.baseline_run_id,
            "current_run_id": self.current_run_id,
            "ruleset_version_changed": self.ruleset_version_changed,
            "findings": [f.to_dict() for f in self.findings],
        }


def compare_runs(
    baseline: AssessmentRun,
    current: AssessmentRun,
    *,
    score_threshold: float = 5.0,
    coverage_threshold: float = 0.05,
) -> TrendReport:
    """Compare two runs and classify object changes.

    Coverage loss takes precedence over quality regression. If the current score
    drops because the object became less observable, the programme should fix
    collection before blaming the object owner.
    """

    if score_threshold < 0:
        raise ValueError("score_threshold must be non-negative")
    if coverage_threshold < 0:
        raise ValueError("coverage_threshold must be non-negative")

    ruleset_changed = baseline.ruleset_version != current.ruleset_version
    baseline_cards = _cards_by_id(baseline.scorecards)
    current_cards = _cards_by_id(current.scorecards)

    findings: list[TrendFinding] = []
    for object_id in sorted(set(baseline_cards) | set(current_cards)):
        old = baseline_cards.get(object_id)
        new = current_cards.get(object_id)
        if old is None and new is not None:
            findings.append(_new_object(baseline, current, new))
        elif old is not None and new is None:
            findings.append(_removed_object(baseline, current, old))
        elif old is not None and new is not None:
            findings.append(
                _compare_card(
                    baseline,
                    current,
                    old,
                    new,
                    ruleset_changed=ruleset_changed,
                    score_threshold=score_threshold,
                    coverage_threshold=coverage_threshold,
                )
            )
    return TrendReport(
        baseline_run_id=baseline.run_id,
        current_run_id=current.run_id,
        ruleset_version_changed=ruleset_changed,
        findings=findings,
    )


def _cards_by_id(cards: Iterable[Scorecard]) -> dict[str, Scorecard]:
    return {card.object_id: card for card in cards}


def _new_object(baseline: AssessmentRun, current: AssessmentRun, card: Scorecard) -> TrendFinding:
    return TrendFinding(
        object_id=card.object_id,
        object_name=card.object_name,
        object_type=card.object_type.value,
        baseline_run_id=baseline.run_id,
        current_run_id=current.run_id,
        classification=TrendClassification.NEW_OBJECT,
        current_score=round(card.score, 2),
        current_coverage=round(card.coverage, 4),
        current_confidence=round(card.confidence, 4),
        detail="Object appears in the current run but not the baseline run.",
    )


def _removed_object(baseline: AssessmentRun, current: AssessmentRun, card: Scorecard) -> TrendFinding:
    return TrendFinding(
        object_id=card.object_id,
        object_name=card.object_name,
        object_type=card.object_type.value,
        baseline_run_id=baseline.run_id,
        current_run_id=current.run_id,
        classification=TrendClassification.REMOVED_OBJECT,
        baseline_score=round(card.score, 2),
        baseline_coverage=round(card.coverage, 4),
        baseline_confidence=round(card.confidence, 4),
        detail="Object existed in the baseline run but not the current run.",
    )


def _compare_card(
    baseline: AssessmentRun,
    current: AssessmentRun,
    old: Scorecard,
    new: Scorecard,
    *,
    ruleset_changed: bool,
    score_threshold: float,
    coverage_threshold: float,
) -> TrendFinding:
    score_delta = round(new.score - old.score, 2)
    confidence_delta = round(new.confidence - old.confidence, 4)
    coverage_delta = round(new.coverage - old.coverage, 4)
    classification = _classify_delta(
        score_delta=score_delta,
        coverage_delta=coverage_delta,
        ruleset_changed=ruleset_changed,
        score_threshold=score_threshold,
        coverage_threshold=coverage_threshold,
    )
    return TrendFinding(
        object_id=new.object_id,
        object_name=new.object_name,
        object_type=new.object_type.value,
        baseline_run_id=baseline.run_id,
        current_run_id=current.run_id,
        classification=classification,
        score_delta=score_delta,
        confidence_delta=confidence_delta,
        coverage_delta=coverage_delta,
        baseline_score=round(old.score, 2),
        current_score=round(new.score, 2),
        baseline_coverage=round(old.coverage, 4),
        current_coverage=round(new.coverage, 4),
        baseline_confidence=round(old.confidence, 4),
        current_confidence=round(new.confidence, 4),
        detail=_detail(classification, score_delta, coverage_delta),
    )


def _classify_delta(
    *,
    score_delta: float,
    coverage_delta: float,
    ruleset_changed: bool,
    score_threshold: float,
    coverage_threshold: float,
) -> TrendClassification:
    if ruleset_changed:
        return TrendClassification.RULESET_CHANGED
    if coverage_delta <= -coverage_threshold:
        return TrendClassification.COVERAGE_LOSS
    if coverage_delta >= coverage_threshold and abs(score_delta) < score_threshold:
        return TrendClassification.COVERAGE_GAIN
    if score_delta <= -score_threshold:
        return TrendClassification.QUALITY_REGRESSION
    if score_delta >= score_threshold:
        return TrendClassification.IMPROVED
    return TrendClassification.UNCHANGED


def _detail(
    classification: TrendClassification,
    score_delta: float,
    coverage_delta: float,
) -> str:
    if classification is TrendClassification.COVERAGE_LOSS:
        return "Coverage dropped; treat this as a collection incident before judging quality."
    if classification is TrendClassification.QUALITY_REGRESSION:
        return "Score dropped while coverage remained stable enough to compare quality."
    if classification is TrendClassification.RULESET_CHANGED:
        return "Ruleset version changed; do not compare scores without migration notes."
    if classification is TrendClassification.COVERAGE_GAIN:
        return "Coverage improved without a material score change."
    if classification is TrendClassification.IMPROVED:
        return "Score improved while coverage remained comparable."
    return f"Score delta {score_delta:+.2f}, coverage delta {coverage_delta:+.4f}."
