"""Core data model shared by collectors, rules, scoring and reporting.

Design rules enforced here:

1.  A score is never published without its evidence, its coverage and the
    ruleset version that produced it.
2.  Missing evidence yields ``NOT_EVALUATED``, never a zero and never a pass.
3.  A blocking finding caps the published score; a good average can never
    neutralise a blocking rule.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ObjectType(str, Enum):
    """Assessable object types."""

    TENANT = "tenant"
    CAPACITY = "capacity"
    WORKSPACE = "workspace"
    SEMANTIC_MODEL = "semantic_model"
    REPORT = "report"
    DATA_AGENT = "data_agent"


class Severity(str, Enum):
    """Finding severity.

    ``BLOCKING`` and ``MAJOR`` apply a hard cap on the published score.
    """

    BLOCKING = "blocking"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


SEVERITY_ORDER = {
    Severity.BLOCKING: 0,
    Severity.MAJOR: 1,
    Severity.MINOR: 2,
    Severity.INFO: 3,
}

#: Score ceilings applied when a rule of that severity fails.
SEVERITY_SCORE_CAP = {
    Severity.BLOCKING: 39.0,
    Severity.MAJOR: 59.0,
}


class RuleStatus(str, Enum):
    """Outcome of a single rule evaluation."""

    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    NOT_EVALUATED = "not_evaluated"
    NOT_APPLICABLE = "not_applicable"


class ReadinessStatus(str, Enum):
    """Published readiness class of an object."""

    READY = "ready"
    READY_WITH_CONDITIONS = "ready_with_conditions"
    REMEDIATION_REQUIRED = "remediation_required"
    NOT_READY = "not_ready"
    NOT_EVALUATED = "not_evaluated"


class Dimension(str, Enum):
    """Scoring dimensions. Weights per object type live in ``scoring.py``."""

    SECURITY = "security"
    GOVERNANCE = "governance"
    ARCHITECTURE = "architecture"
    AI_READINESS = "ai_readiness"
    BUSINESS_SEMANTICS = "business_semantics"
    VISUAL_QUALITY = "visual_quality"
    FUNCTIONAL_QUALITY = "functional_quality"
    OPERATIONS = "operations"
    PERFORMANCE = "performance"
    COVERAGE = "coverage"


class Effort(str, Enum):
    """Remediation effort bucket."""

    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


@dataclass(frozen=True)
class Evidence:
    """A traceable proof backing a rule outcome.

    ``source`` identifies the collector (``scanner_api``, ``fabric_rest``,
    ``activity_events``, ``agent_eval``, ``offline_fixture``). ``reference``
    points at the exact payload path so a reviewer can reproduce the finding.
    """

    source: str
    reference: str
    collected_at: str = field(default_factory=utcnow)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RuleOutcome:
    """Result of evaluating one rule against one object.

    ``score`` is a 0.0-1.0 quality ratio. ``PARTIAL`` allows graded rules such
    as "percentage of visible measures carrying a description".
    """

    status: RuleStatus
    score: float = 0.0
    detail: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    observed: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def passed(cls, detail: str = "", **kwargs: Any) -> "RuleOutcome":
        return cls(status=RuleStatus.PASSED, score=1.0, detail=detail, **kwargs)

    @classmethod
    def failed(cls, detail: str = "", **kwargs: Any) -> "RuleOutcome":
        return cls(status=RuleStatus.FAILED, score=0.0, detail=detail, **kwargs)

    @classmethod
    def partial(cls, score: float, detail: str = "", **kwargs: Any) -> "RuleOutcome":
        clamped = max(0.0, min(1.0, float(score)))
        return cls(status=RuleStatus.PARTIAL, score=clamped, detail=detail, **kwargs)

    @classmethod
    def not_evaluated(cls, reason: str, **kwargs: Any) -> "RuleOutcome":
        """Evidence is missing or unreadable. Never treated as a pass or a zero."""
        return cls(status=RuleStatus.NOT_EVALUATED, score=0.0, detail=reason, **kwargs)

    @classmethod
    def not_applicable(cls, reason: str, **kwargs: Any) -> "RuleOutcome":
        """The rule does not apply to this object (e.g. no date logic in the model)."""
        return cls(status=RuleStatus.NOT_APPLICABLE, score=0.0, detail=reason, **kwargs)

    @property
    def counts_towards_score(self) -> bool:
        return self.status in (RuleStatus.PASSED, RuleStatus.FAILED, RuleStatus.PARTIAL)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "score": round(self.score, 4),
            "detail": self.detail,
            "observed": self.observed,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class Finding:
    """A rule outcome bound to an object, ready for the remediation backlog."""

    rule_id: str
    title: str
    object_id: str
    object_name: str
    object_type: ObjectType
    dimension: Dimension
    severity: Severity
    outcome: RuleOutcome
    remediation: str = ""
    effort: Effort = Effort.M
    docs: str = ""
    owner_role: str = ""

    @property
    def is_failure(self) -> bool:
        return self.outcome.status is RuleStatus.FAILED

    @property
    def is_blocking(self) -> bool:
        return self.is_failure and self.severity is Severity.BLOCKING

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "object_id": self.object_id,
            "object_name": self.object_name,
            "object_type": self.object_type.value,
            "dimension": self.dimension.value,
            "severity": self.severity.value,
            "remediation": self.remediation,
            "effort": self.effort.value,
            "owner_role": self.owner_role,
            "docs": self.docs,
            "outcome": self.outcome.to_dict(),
        }


@dataclass
class Scorecard:
    """Published assessment of a single object.

    ``eligible`` is independent from ``score``: an object with a high score but
    a failed blocking rule stays ineligible.
    """

    object_id: str
    object_name: str
    object_type: ObjectType
    score: float
    raw_score: float
    status: ReadinessStatus
    eligible: bool
    confidence: float
    coverage: float
    dimension_scores: dict[str, float] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    ruleset_version: str = ""
    assessed_at: str = field(default_factory=utcnow)
    notes: list[str] = field(default_factory=list)
    parent_id: str = ""

    @property
    def blocking_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.is_blocking]

    @property
    def failed_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.is_failure]

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "object_name": self.object_name,
            "object_type": self.object_type.value,
            "parent_id": self.parent_id,
            "score": round(self.score, 2),
            "raw_score": round(self.raw_score, 2),
            "status": self.status.value,
            "eligible": self.eligible,
            "confidence": round(self.confidence, 4),
            "coverage": round(self.coverage, 4),
            "dimension_scores": {k: round(v, 2) for k, v in self.dimension_scores.items()},
            "ruleset_version": self.ruleset_version,
            "assessed_at": self.assessed_at,
            "notes": self.notes,
            "blocking_findings": [f.rule_id for f in self.blocking_findings],
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class AssessmentRun:
    """A complete assessment execution: every scorecard plus run provenance."""

    run_id: str
    tenant_id: str
    started_at: str = field(default_factory=utcnow)
    completed_at: str = ""
    ruleset_version: str = ""
    collector_mode: str = "offline"
    scorecards: list[Scorecard] = field(default_factory=list)
    collection_errors: list[dict[str, Any]] = field(default_factory=list)

    def by_type(self, object_type: ObjectType) -> list[Scorecard]:
        return [s for s in self.scorecards if s.object_type is object_type]

    def get(self, object_id: str) -> Scorecard | None:
        for card in self.scorecards:
            if card.object_id == object_id:
                return card
        return None

    @property
    def blocking_findings(self) -> list[Finding]:
        out: list[Finding] = []
        for card in self.scorecards:
            out.extend(card.blocking_findings)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "ruleset_version": self.ruleset_version,
            "collector_mode": self.collector_mode,
            "collection_errors": self.collection_errors,
            # Surfaced whole at run level: these are the walls a reader must see before
            # any score. Scorecards carry only the rule ids to avoid duplicating them.
            "blocking_findings": [f.to_dict() for f in self.blocking_findings],
            "scorecards": [s.to_dict() for s in self.scorecards],
        }

    def to_json(self, path: str | None = None, indent: int = 2) -> str:
        payload = json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
        return payload
