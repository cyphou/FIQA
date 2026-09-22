"""Scoring engine: rule outcomes to explainable scorecards.

Three results are published side by side and never collapsed into one number:

* **eligibility** — pass/fail on blocking rules;
* **readiness score** — 0-100 weighted quality;
* **confidence** — how much of the rule set could actually be evaluated.

A blocking failure caps the published score at 39 and forces ``NOT_READY``.
A major failure caps it at 59. Insufficient evidence yields ``NOT_EVALUATED``
rather than an invented zero.
"""

from __future__ import annotations

from fabric_iq import RULESET_VERSION
from fabric_iq.errors import ScoringError
from fabric_iq.models import (
    AssessmentRun,
    Dimension,
    Finding,
    ObjectType,
    ReadinessStatus,
    RuleStatus,
    Scorecard,
    SEVERITY_SCORE_CAP,
    Severity,
)
from fabric_iq.rules.base import RuleRegistry, registry as default_registry

#: Dimension weights per object type. Each mapping must sum to 1.0.
DIMENSION_WEIGHTS: dict[ObjectType, dict[Dimension, float]] = {
    ObjectType.TENANT: {
        Dimension.AI_READINESS: 0.25,
        Dimension.ARCHITECTURE: 0.20,
        Dimension.SECURITY: 0.20,
        Dimension.GOVERNANCE: 0.15,
        Dimension.COVERAGE: 0.10,
        Dimension.OPERATIONS: 0.10,
    },
    ObjectType.WORKSPACE: {
        Dimension.GOVERNANCE: 0.30,
        Dimension.SECURITY: 0.25,
        Dimension.ARCHITECTURE: 0.20,
        Dimension.OPERATIONS: 0.15,
        Dimension.COVERAGE: 0.10,
    },
    ObjectType.SEMANTIC_MODEL: {
        Dimension.ARCHITECTURE: 0.25,
        Dimension.AI_READINESS: 0.25,
        Dimension.SECURITY: 0.15,
        Dimension.BUSINESS_SEMANTICS: 0.15,
        Dimension.PERFORMANCE: 0.10,
        Dimension.COVERAGE: 0.10,
    },
    ObjectType.REPORT: {
        Dimension.ARCHITECTURE: 0.30,
        Dimension.VISUAL_QUALITY: 0.20,
        Dimension.FUNCTIONAL_QUALITY: 0.20,
        Dimension.GOVERNANCE: 0.20,
        Dimension.OPERATIONS: 0.10,
    },
    ObjectType.DATA_AGENT: {
        Dimension.FUNCTIONAL_QUALITY: 0.25,
        Dimension.SECURITY: 0.20,
        Dimension.AI_READINESS: 0.15,
        Dimension.ARCHITECTURE: 0.15,
        Dimension.BUSINESS_SEMANTICS: 0.15,
        Dimension.OPERATIONS: 0.10,
    },
}

#: Readiness class thresholds, highest first.
STATUS_THRESHOLDS: tuple[tuple[float, ReadinessStatus], ...] = (
    (85.0, ReadinessStatus.READY),
    (70.0, ReadinessStatus.READY_WITH_CONDITIONS),
    (50.0, ReadinessStatus.REMEDIATION_REQUIRED),
    (0.0, ReadinessStatus.NOT_READY),
)

#: Below this weighted rule coverage an object is reported as NOT_EVALUATED.
MIN_COVERAGE_TO_PUBLISH = 0.50

#: Aggregation weights for rolled-up scores.
WORKSPACE_ROLLUP = {"objects": 0.70, "own_rules": 0.20, "coverage": 0.10}
TENANT_ROLLUP = {"workspaces": 0.60, "own_rules": 0.25, "coverage": 0.15}


def _validate_weights() -> None:
    for object_type, weights in DIMENSION_WEIGHTS.items():
        total = round(sum(weights.values()), 6)
        if total != 1.0:
            raise ScoringError(f"dimension weights for {object_type.value} sum to {total}, expected 1.0")


_validate_weights()


def status_for(score: float) -> ReadinessStatus:
    """Map a 0-100 score to its published readiness class."""
    for threshold, status in STATUS_THRESHOLDS:
        if score >= threshold:
            return status
    return ReadinessStatus.NOT_READY


class ScoringEngine:
    """Applies a rule registry to normalized objects and produces scorecards."""

    def __init__(
        self,
        rules: RuleRegistry | None = None,
        ruleset_version: str = RULESET_VERSION,
    ) -> None:
        self.rules = rules or default_registry
        self.ruleset_version = ruleset_version

    # ── object-level scoring ──────────────────────────────────────

    def score_object(self, subject: dict, object_type: ObjectType) -> Scorecard:
        """Evaluate every rule of ``object_type`` against ``subject``."""
        weights = DIMENSION_WEIGHTS.get(object_type)
        if weights is None:
            raise ScoringError(f"no dimension weights defined for {object_type.value}")

        object_id = subject.get("id") or subject.get("object_id") or ""
        object_name = subject.get("name") or object_id
        if not object_id:
            raise ScoringError(f"{object_type.value} subject has no id")

        findings: list[Finding] = []
        # dimension -> [(weight, score)] for rules that actually produced a score
        scored: dict[Dimension, list[tuple[float, float]]] = {}
        evaluated_weight = 0.0
        applicable_weight = 0.0

        for rule in self.rules.for_type(object_type):
            outcome = rule.evaluate(subject)
            findings.append(
                Finding(
                    rule_id=rule.id,
                    title=rule.title,
                    object_id=object_id,
                    object_name=object_name,
                    object_type=object_type,
                    dimension=rule.dimension,
                    severity=rule.severity,
                    outcome=outcome,
                    remediation=rule.remediation,
                    effort=rule.effort,
                    docs=rule.docs,
                    owner_role=rule.owner_role,
                )
            )
            if outcome.status is RuleStatus.NOT_APPLICABLE:
                continue
            applicable_weight += rule.weight
            if outcome.counts_towards_score:
                evaluated_weight += rule.weight
                scored.setdefault(rule.dimension, []).append((rule.weight, outcome.score))

        coverage = evaluated_weight / applicable_weight if applicable_weight > 0 else 0.0
        dimension_scores = self._dimension_scores(scored)
        raw_score = self._weighted_score(dimension_scores, weights)
        score, status, eligible, notes = self._apply_caps(raw_score, findings, coverage)

        return Scorecard(
            object_id=object_id,
            object_name=object_name,
            object_type=object_type,
            parent_id=subject.get("parent_id", ""),
            score=score,
            raw_score=raw_score,
            status=status,
            eligible=eligible,
            confidence=self._confidence(coverage, findings),
            coverage=coverage,
            dimension_scores={d.value: v for d, v in dimension_scores.items()},
            findings=findings,
            ruleset_version=self.ruleset_version,
            notes=notes,
        )

    @staticmethod
    def _dimension_scores(
        scored: dict[Dimension, list[tuple[float, float]]],
    ) -> dict[Dimension, float]:
        out: dict[Dimension, float] = {}
        for dimension, entries in scored.items():
            total_weight = sum(w for w, _ in entries)
            if total_weight <= 0:
                continue
            out[dimension] = 100.0 * sum(w * s for w, s in entries) / total_weight
        return out

    @staticmethod
    def _weighted_score(
        dimension_scores: dict[Dimension, float],
        weights: dict[Dimension, float],
    ) -> float:
        # Renormalize over the dimensions that actually produced a score, so an
        # unobservable dimension lowers confidence rather than the score itself.
        active = {d: w for d, w in weights.items() if d in dimension_scores}
        total_weight = sum(active.values())
        if total_weight <= 0:
            return 0.0
        return sum(dimension_scores[d] * w for d, w in active.items()) / total_weight

    @staticmethod
    def _apply_caps(
        raw_score: float,
        findings: list[Finding],
        coverage: float,
    ) -> tuple[float, ReadinessStatus, bool, list[str]]:
        notes: list[str] = []
        score = raw_score
        blocking = [f for f in findings if f.is_blocking]
        major = [f for f in findings if f.is_failure and f.severity is Severity.MAJOR]

        # A blocking finding is positive evidence: the wall was observed. Thin coverage
        # means we cannot judge quality, never that the wall stopped existing, so the
        # cap is applied before the publication floor is considered.
        if blocking:
            cap = SEVERITY_SCORE_CAP[Severity.BLOCKING]
            score = min(score, cap)
            notes.append(
                f"{len(blocking)} blocking finding(s) cap the score at {cap:.0f}: "
                + ", ".join(f.rule_id for f in blocking)
            )
            if coverage < MIN_COVERAGE_TO_PUBLISH:
                notes.append(
                    f"coverage {coverage:.0%} is below the "
                    f"{MIN_COVERAGE_TO_PUBLISH:.0%} publication floor, but the blocking "
                    "finding is conclusive on its own"
                )
            return score, ReadinessStatus.NOT_READY, False, notes

        if coverage < MIN_COVERAGE_TO_PUBLISH:
            notes.append(
                f"coverage {coverage:.0%} below the {MIN_COVERAGE_TO_PUBLISH:.0%} publication floor"
            )
            return raw_score, ReadinessStatus.NOT_EVALUATED, False, notes

        if major:
            cap = SEVERITY_SCORE_CAP[Severity.MAJOR]
            score = min(score, cap)
            notes.append(
                f"{len(major)} major finding(s) cap the score at {cap:.0f}: "
                + ", ".join(f.rule_id for f in major)
            )

        return score, status_for(score), True, notes

    @staticmethod
    def _confidence(coverage: float, findings: list[Finding]) -> float:
        """Confidence blends rule coverage with the absence of evidence gaps."""
        applicable = [f for f in findings if f.outcome.status is not RuleStatus.NOT_APPLICABLE]
        if not applicable:
            return 0.0
        unevaluated = [f for f in applicable if f.outcome.status is RuleStatus.NOT_EVALUATED]
        evidence_backed = [f for f in applicable if f.outcome.evidence]
        evidence_ratio = len(evidence_backed) / len(applicable)
        gap_penalty = len(unevaluated) / len(applicable)
        return max(0.0, min(1.0, 0.6 * coverage + 0.4 * evidence_ratio - 0.2 * gap_penalty))

    # ── aggregation ───────────────────────────────────────────────

    def rollup_workspace(self, workspace: Scorecard, children: list[Scorecard]) -> Scorecard:
        """Blend a workspace's own rules with the objects it contains."""
        return self._rollup(workspace, children, WORKSPACE_ROLLUP, "objects")

    def rollup_tenant(self, tenant: Scorecard, workspaces: list[Scorecard]) -> Scorecard:
        """Blend the tenant's own rules with its workspace scores."""
        return self._rollup(tenant, workspaces, TENANT_ROLLUP, "workspaces")

    @staticmethod
    def _rollup(
        parent: Scorecard,
        children: list[Scorecard],
        weights: dict[str, float],
        child_key: str,
    ) -> Scorecard:
        publishable = [c for c in children if c.status is not ReadinessStatus.NOT_EVALUATED]
        if not publishable:
            parent.notes.append(f"no publishable {child_key} to aggregate; score reflects own rules only")
            return parent

        # Criticality weighting keeps a critical broken object visible inside a
        # large portfolio of healthy ones.
        total_weight = sum(max(1.0, c.confidence) for c in publishable)
        child_score = sum(c.score * max(1.0, c.confidence) for c in publishable) / total_weight
        child_coverage = sum(c.coverage for c in publishable) / len(publishable)

        blended = (
            weights[child_key] * child_score
            + weights["own_rules"] * parent.raw_score
            + weights["coverage"] * (100.0 * child_coverage)
        )

        inherited_blocking = [c for c in children if c.blocking_findings]
        parent.raw_score = blended
        parent.score = blended
        parent.notes.append(
            f"rolled up from {len(publishable)} {child_key} "
            f"(mean {child_score:.1f}/100, coverage {child_coverage:.0%})"
        )

        if parent.blocking_findings:
            parent.score = min(parent.score, SEVERITY_SCORE_CAP[Severity.BLOCKING])
            parent.status = ReadinessStatus.NOT_READY
            parent.eligible = False
        elif inherited_blocking:
            parent.score = min(parent.score, SEVERITY_SCORE_CAP[Severity.MAJOR])
            parent.status = status_for(parent.score)
            parent.eligible = True
            parent.notes.append(
                f"{len(inherited_blocking)} child object(s) carry blocking findings: "
                + ", ".join(c.object_name for c in inherited_blocking[:10])
            )
        else:
            parent.status = status_for(parent.score)

        parent.coverage = min(parent.coverage, child_coverage) if parent.coverage else child_coverage
        return parent


def assess(
    inventory: dict,
    *,
    run_id: str,
    collector_mode: str = "offline",
    rules: RuleRegistry | None = None,
) -> AssessmentRun:
    """Score a full normalized inventory and roll the results up.

    ``inventory`` is the Silver-layer structure produced by
    ``fabric_iq.collectors``: a tenant dict plus lists of workspaces, semantic
    models, reports and data agents, each carrying ``id`` and ``parent_id``.
    """
    engine = ScoringEngine(rules=rules)
    tenant = inventory.get("tenant") or {}
    if not tenant:
        raise ScoringError("inventory has no tenant section")

    run = AssessmentRun(
        run_id=run_id,
        tenant_id=tenant.get("id", ""),
        ruleset_version=engine.ruleset_version,
        collector_mode=collector_mode,
        collection_errors=list(inventory.get("collection_errors") or []),
    )

    # Leaf objects first: workspace and tenant rollups depend on their scores.
    # A present-but-None key means "not observed", so `or []` is required here:
    # `.get(key, [])` would hand back None and iteration would explode.
    models = [engine.score_object(m, ObjectType.SEMANTIC_MODEL) for m in inventory.get("semantic_models") or []]
    model_scores = {m.object_id: m.score for m in models}

    reports = []
    for report in inventory.get("reports") or []:
        enriched = dict(report)
        enriched.setdefault("semantic_model_score", model_scores.get(report.get("semantic_model_id")))
        enriched["semantic_model_reachable"] = report.get("semantic_model_id") in model_scores
        reports.append(engine.score_object(enriched, ObjectType.REPORT))

    agents = []
    for agent in inventory.get("data_agents") or []:
        enriched = dict(agent)
        sources = agent.get("data_sources")
        if isinstance(sources, list) and "source_scores" not in enriched:
            enriched["source_scores"] = {
                src.get("id"): model_scores.get(src.get("id"))
                for src in sources
                if src.get("type") == "semantic_model"
            }
        agents.append(engine.score_object(enriched, ObjectType.DATA_AGENT))

    leaves = models + reports + agents
    run.scorecards.extend(leaves)

    workspaces = []
    for workspace in inventory.get("workspaces") or []:
        card = engine.score_object(workspace, ObjectType.WORKSPACE)
        children = [leaf for leaf in leaves if leaf.parent_id == card.object_id]
        workspaces.append(engine.rollup_workspace(card, children))
    run.scorecards.extend(workspaces)

    tenant_card = engine.score_object(tenant, ObjectType.TENANT)
    run.scorecards.append(engine.rollup_tenant(tenant_card, workspaces))

    from fabric_iq.models import utcnow

    run.completed_at = utcnow()
    return run
