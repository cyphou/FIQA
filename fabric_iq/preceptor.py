"""Preceptorship loop — quality gate over an assessment run.

Ported from the Tableau to Power BI migration project and adapted: here the
reviewed artifact is the **assessment itself**, not a generated report. The
loop answers one question: *can this readiness verdict be trusted and acted
upon?*

```
DRAFT (Assessor) -> REVIEW (Preceptor) -> APPROVE? (>= 4 stars?)
     ^                                        |
     |                YES --------------------> PUBLISH
     |                 NO --------------------> COACH (feedback)
     |                                            |
     +--------------------------------------------+
                   (max 3 cycles, then escalate)
```

The preceptor is read-only. It never edits a scorecard and never lowers a
threshold to force an approval.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from fabric_iq.errors import ReviewError
from fabric_iq.models import (
    AssessmentRun,
    ObjectType,
    ReadinessStatus,
    RuleStatus,
    Scorecard,
    Severity,
    utcnow,
)

#: The six dimensions the preceptor scores, 1-5 stars each.
DIMENSIONS = (
    "evidence_completeness",
    "rule_coverage",
    "blocking_integrity",
    "remediation_actionability",
    "score_traceability",
    "freshness",
)

#: Minimum average star rating required to publish a run.
MIN_PASS_SCORE = 4.0

#: Maximum review cycles before escalating to a human decision.
MAX_CYCLES = 3

#: Evidence older than this is no longer a reliable basis for a go-live decision.
MAX_EVIDENCE_AGE_HOURS = 48

#: Owning agent for each dimension, used to address coaching feedback.
DIMENSION_OWNER = {
    "evidence_completeness": "@collector",
    "rule_coverage": "@collector",
    "blocking_integrity": "@scorer",
    "remediation_actionability": "@remediation",
    "score_traceability": "@scorer",
    "freshness": "@orchestrator",
}


def _stars(ratio: float) -> float:
    """Map a 0-1 quality ratio onto the 1-5 star scale."""
    clamped = max(0.0, min(1.0, ratio))
    return round(1.0 + 4.0 * clamped, 2)


@dataclass
class CoachingItem:
    """One actionable defect found in the assessment run."""

    dimension: str
    score: float
    issue: str
    location: str
    fix: str
    owner: str = ""

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            raise ReviewError(f"unknown review dimension: {self.dimension}")
        if not self.owner:
            self.owner = DIMENSION_OWNER.get(self.dimension, "@orchestrator")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "score": self.score,
            "issue": self.issue,
            "location": self.location,
            "fix": self.fix,
            "owner": self.owner,
        }

    def to_console(self, cycle: int, max_cycles: int) -> str:
        return (
            f"COACH FEEDBACK - Cycle {cycle}/{max_cycles}\n"
            f"{'=' * 60}\n"
            f"Dimension: {self.dimension} - {self.score}*\n"
            f"Owner:     {self.owner}\n"
            f"Issue:     {self.issue}\n"
            f"Location:  {self.location}\n"
            f"Fix:       {self.fix}\n"
        )


@dataclass
class ReviewScorecard:
    """Per-dimension star ratings for one review cycle."""

    scores: dict[str, float] = field(default_factory=dict)

    def set(self, dimension: str, value: float) -> None:
        if dimension not in DIMENSIONS:
            raise ReviewError(f"unknown review dimension: {dimension}")
        if not 0.0 <= value <= 5.0:
            raise ReviewError(f"review score for {dimension} must be within 0-5, got {value}")
        self.scores[dimension] = value

    def average(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(self.scores.values()) / len(self.scores), 2)

    def passed(self, threshold: float = MIN_PASS_SCORE) -> bool:
        return self.average() >= threshold

    def weakest(self) -> str:
        if not self.scores:
            return ""
        return min(self.scores, key=lambda k: self.scores[k])

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": dict(self.scores),
            "average": self.average(),
            "passed": self.passed(),
        }


@dataclass
class ReviewReport:
    """Outcome of the full preceptorship loop over one assessment run."""

    run_id: str
    cycles: list[ReviewScorecard] = field(default_factory=list)
    coaching: list[list[CoachingItem]] = field(default_factory=list)
    verdict: str = "pending"
    reviewed_at: str = field(default_factory=utcnow)

    @property
    def final(self) -> ReviewScorecard:
        if not self.cycles:
            raise ReviewError("review report has no cycle")
        return self.cycles[-1]

    @property
    def approved(self) -> bool:
        return self.verdict == "approved"

    def open_items(self) -> list[CoachingItem]:
        return list(self.coaching[-1]) if self.coaching else []

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "verdict": self.verdict,
            "reviewed_at": self.reviewed_at,
            "cycles": [c.to_dict() for c in self.cycles],
            "coaching": [[i.to_dict() for i in cycle] for cycle in self.coaching],
        }

    def to_json(self, path: str | None = None, indent: int = 2) -> str:
        payload = json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
        return payload

    def to_console(self) -> str:
        lines = [
            "",
            "PRECEPTORSHIP REVIEW",
            "=" * 60,
            f"Run:     {self.run_id}",
            f"Verdict: {self.verdict.upper()}",
            f"Cycles:  {len(self.cycles)}",
            "",
        ]
        final = self.final
        for dimension in DIMENSIONS:
            score = final.scores.get(dimension)
            if score is None:
                continue
            filled = int(round(score))
            lines.append(f"  {dimension:<28} {'*' * filled:<5} {score}")
        lines.append("")
        lines.append(f"  {'AVERAGE':<28} {final.average()} / 5.0 (threshold {MIN_PASS_SCORE})")
        lines.append("")
        for item in self.open_items():
            lines.append(item.to_console(len(self.cycles), MAX_CYCLES))
        return "\n".join(lines)


class PreceptorLoop:
    """Reviews an assessment run and coaches the owning agents."""

    def __init__(self, threshold: float = MIN_PASS_SCORE) -> None:
        self.threshold = threshold

    # ── single cycle ──────────────────────────────────────────────

    def review(self, run: AssessmentRun) -> tuple[ReviewScorecard, list[CoachingItem]]:
        """Score one cycle and return its coaching items."""
        if not run.scorecards:
            raise ReviewError("cannot review a run with no scorecard")

        card = ReviewScorecard()
        coaching: list[CoachingItem] = []

        for check in (
            self._check_evidence_completeness,
            self._check_rule_coverage,
            self._check_blocking_integrity,
            self._check_remediation_actionability,
            self._check_score_traceability,
            self._check_freshness,
        ):
            dimension, score, item = check(run)
            card.set(dimension, score)
            if item is not None and score < self.threshold:
                coaching.append(item)

        return card, coaching

    def run(self, run: AssessmentRun, max_cycles: int = MAX_CYCLES) -> ReviewReport:
        """Run up to ``max_cycles`` review cycles.

        The loop does not repair the run itself: a repeated cycle only makes
        sense when the caller applied the coaching feedback in between. It is
        therefore safe and honest to escalate as soon as a cycle fails twice
        with identical findings.
        """
        if max_cycles < 1:
            raise ReviewError("max_cycles must be at least 1")

        report = ReviewReport(run_id=run.run_id)
        previous_signature: tuple[str, ...] | None = None

        for _ in range(max_cycles):
            card, coaching = self.review(run)
            report.cycles.append(card)
            report.coaching.append(coaching)

            if card.passed(self.threshold):
                report.verdict = "approved"
                return report

            signature = tuple(sorted(f"{i.dimension}:{i.issue}" for i in coaching))
            if signature == previous_signature:
                # Nothing changed between cycles; looping again proves nothing.
                break
            previous_signature = signature

        report.verdict = "escalated"
        return report

    # ── dimension checks ──────────────────────────────────────────

    @staticmethod
    def _check_evidence_completeness(run: AssessmentRun):
        findings = [f for card in run.scorecards for f in card.findings]
        applicable = [f for f in findings if f.outcome.status is not RuleStatus.NOT_APPLICABLE]
        if not applicable:
            return "evidence_completeness", 1.0, CoachingItem(
                "evidence_completeness", 1.0,
                "no applicable rule produced a finding",
                f"run {run.run_id}",
                "Verify the collector actually returned an inventory before scoring.",
            )
        backed = [f for f in applicable if f.outcome.evidence]
        ratio = len(backed) / len(applicable)
        score = _stars(ratio)
        unbacked = sorted({f.rule_id for f in applicable if not f.outcome.evidence})
        return "evidence_completeness", score, CoachingItem(
            "evidence_completeness", score,
            f"{len(applicable) - len(backed)}/{len(applicable)} findings carry no evidence reference",
            f"rules: {', '.join(unbacked[:8])}",
            "Attach an Evidence(source, reference) to every rule outcome so a reviewer can reproduce it.",
        )

    @staticmethod
    def _check_rule_coverage(run: AssessmentRun):
        cards = run.scorecards
        coverage = sum(c.coverage for c in cards) / len(cards)
        score = _stars(coverage)
        weak = sorted(
            (c for c in cards if c.coverage < 0.8),
            key=lambda c: c.coverage,
        )
        return "rule_coverage", score, CoachingItem(
            "rule_coverage", score,
            f"mean rule coverage is {coverage:.0%}; {len(weak)} object(s) below 80%",
            ", ".join(f"{c.object_name} ({c.coverage:.0%})" for c in weak[:8]) or "n/a",
            "Collect the missing evidence (scanner sub-metadata, PBIP Copilot folder, agent evaluation) and re-run.",
        )

    @staticmethod
    def _check_blocking_integrity(run: AssessmentRun):
        """No object may be published as ready while a blocking rule failed."""
        violations = [
            c
            for c in run.scorecards
            if c.blocking_findings
            and (c.status in (ReadinessStatus.READY, ReadinessStatus.READY_WITH_CONDITIONS) or c.eligible)
        ]
        over_cap = [
            c for c in run.scorecards if c.blocking_findings and c.score > 39.0
        ]
        problems = {c.object_id for c in violations} | {c.object_id for c in over_cap}
        score = 5.0 if not problems else 1.0
        return "blocking_integrity", score, CoachingItem(
            "blocking_integrity", score,
            f"{len(problems)} object(s) published as eligible or above the cap despite a blocking finding",
            ", ".join(sorted(problems)[:8]) or "n/a",
            "Fix the cap logic in scoring.ScoringEngine._apply_caps; a blocking failure must force NOT_READY.",
        )

    @staticmethod
    def _check_remediation_actionability(run: AssessmentRun):
        failures = [f for card in run.scorecards for f in card.failed_findings]
        if not failures:
            return "remediation_actionability", 5.0, None
        actionable = [
            f
            for f in failures
            if f.remediation.strip() and f.owner_role.strip() and f.effort is not None
        ]
        ratio = len(actionable) / len(failures)
        score = _stars(ratio)
        gaps = sorted({f.rule_id for f in failures if f not in actionable})
        return "remediation_actionability", score, CoachingItem(
            "remediation_actionability", score,
            f"{len(failures) - len(actionable)}/{len(failures)} failures lack a remediation, an owner or an effort",
            f"rules: {', '.join(gaps[:8])}",
            "Give every rule a concrete remediation sentence, an owner_role and an Effort bucket.",
        )

    @staticmethod
    def _check_score_traceability(run: AssessmentRun):
        cards = run.scorecards
        traceable = [
            c
            for c in cards
            if c.ruleset_version and c.dimension_scores and c.assessed_at
        ]
        ratio = len(traceable) / len(cards)
        score = _stars(ratio)
        gaps = [c.object_name for c in cards if c not in traceable]
        return "score_traceability", score, CoachingItem(
            "score_traceability", score,
            f"{len(gaps)}/{len(cards)} scorecards lack a ruleset version, dimension breakdown or timestamp",
            ", ".join(gaps[:8]) or "n/a",
            "Stamp every scorecard with the ruleset version, its dimension scores and its assessment timestamp.",
        )

    @staticmethod
    def _check_freshness(run: AssessmentRun):
        if run.collection_errors:
            score = 2.0
            return "freshness", score, CoachingItem(
                "freshness", score,
                f"{len(run.collection_errors)} collection error(s) recorded during this run",
                f"run {run.run_id}",
                "Resolve the collection errors and re-run; a partial collection cannot support a go-live decision.",
            )
        stale = [c for c in run.scorecards if c.confidence < 0.5]
        ratio = 1.0 - (len(stale) / len(run.scorecards))
        score = _stars(ratio)
        return "freshness", score, CoachingItem(
            "freshness", score,
            f"{len(stale)}/{len(run.scorecards)} scorecards have a confidence below 50%",
            ", ".join(c.object_name for c in stale[:8]) or "n/a",
            f"Refresh the evidence (max age {MAX_EVIDENCE_AGE_HOURS}h) and close the evaluation gaps before publishing.",
        )
