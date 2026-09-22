"""Rule definition primitives and the global rule registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from fabric_iq.errors import RuleError
from fabric_iq.models import (
    Dimension,
    Effort,
    Evidence,
    ObjectType,
    RuleOutcome,
    RuleStatus,
    Severity,
)

CheckFn = Callable[[dict], RuleOutcome]


@dataclass(frozen=True)
class Rule:
    """One deterministic readiness check.

    ``weight`` is relative *within* a dimension. The dimension's own weight in
    the object score is defined in ``fabric_iq.scoring``.
    """

    id: str
    title: str
    object_type: ObjectType
    dimension: Dimension
    severity: Severity
    check: CheckFn
    remediation: str
    weight: float = 1.0
    effort: Effort = Effort.M
    owner_role: str = ""
    docs: str = ""

    def evaluate(self, subject: dict) -> RuleOutcome:
        """Run the rule, converting unexpected failures into NOT_EVALUATED.

        A defective rule must degrade the confidence of the run, not crash the
        whole assessment or silently pass the object.
        """
        try:
            outcome = self.check(subject)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            return RuleOutcome.not_evaluated(
                f"rule {self.id} could not be evaluated: {type(exc).__name__}: {exc}"
            )
        if not isinstance(outcome, RuleOutcome):
            raise RuleError(f"rule {self.id} returned {type(outcome)!r}, expected RuleOutcome")
        return outcome


class RuleRegistry:
    """Ordered, de-duplicated catalogue of rules keyed by object type."""

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def register(self, rule: Rule) -> Rule:
        if rule.id in self._rules:
            raise RuleError(f"duplicate rule id: {rule.id}")
        if rule.weight <= 0:
            raise RuleError(f"rule {rule.id} must have a positive weight")
        self._rules[rule.id] = rule
        return rule

    def add(
        self,
        rule_id: str,
        title: str,
        object_type: ObjectType,
        dimension: Dimension,
        severity: Severity,
        remediation: str,
        *,
        weight: float = 1.0,
        effort: Effort = Effort.M,
        owner_role: str = "",
        docs: str = "",
    ) -> Callable[[CheckFn], CheckFn]:
        """Decorator form used by the rule modules."""

        def decorator(fn: CheckFn) -> CheckFn:
            self.register(
                Rule(
                    id=rule_id,
                    title=title,
                    object_type=object_type,
                    dimension=dimension,
                    severity=severity,
                    check=fn,
                    remediation=remediation,
                    weight=weight,
                    effort=effort,
                    owner_role=owner_role,
                    docs=docs,
                )
            )
            return fn

        return decorator

    def for_type(self, object_type: ObjectType) -> list[Rule]:
        return [r for r in self._rules.values() if r.object_type is object_type]

    def get(self, rule_id: str) -> Rule:
        try:
            return self._rules[rule_id]
        except KeyError as exc:
            raise RuleError(f"unknown rule id: {rule_id}") from exc

    def all(self) -> list[Rule]:
        return list(self._rules.values())

    def __len__(self) -> int:
        return len(self._rules)

    def __contains__(self, rule_id: object) -> bool:
        return rule_id in self._rules


registry = RuleRegistry()


# ── Helpers shared by rule modules ────────────────────────────────


def evidence(source: str, reference: str, detail: str = "") -> list[Evidence]:
    """Build a single-item evidence list."""
    return [Evidence(source=source, reference=reference, detail=detail)]


def missing(subject: dict, *keys: str) -> list[str]:
    """Return the keys absent or None in ``subject``."""
    return [k for k in keys if subject.get(k) is None]


def ratio(numerator: float, denominator: float) -> float:
    """Safe ratio; an empty population is a perfect ratio, not a division error."""
    if denominator <= 0:
        return 1.0
    return max(0.0, min(1.0, numerator / denominator))


def require(subject: dict, *keys: str) -> RuleOutcome | None:
    """Return a NOT_EVALUATED outcome when required evidence is absent."""
    absent = missing(subject, *keys)
    if absent:
        return RuleOutcome.not_evaluated(
            "missing evidence: " + ", ".join(sorted(absent)),
            observed={"missing_keys": sorted(absent)},
        )
    return None


def graded(
    score: float,
    detail: str,
    *,
    pass_at: float = 1.0,
    observed: dict[str, Any] | None = None,
    ev: Iterable[Evidence] | None = None,
) -> RuleOutcome:
    """Convert a 0-1 ratio into PASSED / PARTIAL / FAILED.

    A ratio of exactly zero is a failure, not a partial: nothing was done.
    """
    kwargs: dict[str, Any] = {"observed": observed or {}, "evidence": list(ev or [])}
    if score >= pass_at:
        return RuleOutcome.passed(detail, **kwargs)
    if score <= 0.0:
        return RuleOutcome.failed(detail, **kwargs)
    return RuleOutcome.partial(score, detail, **kwargs)


__all__ = [
    "Rule",
    "RuleRegistry",
    "registry",
    "evidence",
    "graded",
    "missing",
    "ratio",
    "require",
    "RuleStatus",
]
