"""Remediation backlog: turn findings into a prioritized, actionable plan.

Priority is deliberately not the raw severity. A blocking finding on a dormant
report matters less than a major finding on the model behind a production
agent, so the ranking blends severity, blast radius and effort.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from typing import Any

from fabric_iq.models import (
    AssessmentRun,
    Effort,
    Finding,
    ObjectType,
    Severity,
)

#: Severity contribution to the priority score.
SEVERITY_SCORE = {
    Severity.BLOCKING: 100.0,
    Severity.MAJOR: 60.0,
    Severity.MINOR: 25.0,
    Severity.INFO: 5.0,
}

#: Blast radius: fixing a tenant setting unblocks everything downstream.
OBJECT_LEVERAGE = {
    ObjectType.TENANT: 2.0,
    ObjectType.CAPACITY: 1.8,
    ObjectType.WORKSPACE: 1.5,
    ObjectType.SEMANTIC_MODEL: 1.4,
    ObjectType.DATA_AGENT: 1.2,
    ObjectType.REPORT: 1.0,
}

#: Effort discount: cheap fixes rise in the backlog at equal impact.
EFFORT_FACTOR = {
    Effort.XS: 1.30,
    Effort.S: 1.15,
    Effort.M: 1.00,
    Effort.L: 0.85,
    Effort.XL: 0.70,
}

#: Indicative person-days per effort bucket, used for capacity planning only.
EFFORT_DAYS = {
    Effort.XS: 0.25,
    Effort.S: 0.5,
    Effort.M: 2.0,
    Effort.L: 5.0,
    Effort.XL: 15.0,
}


@dataclass
class RemediationItem:
    """One backlog entry derived from a failed finding."""

    rule_id: str
    title: str
    object_id: str
    object_name: str
    object_type: ObjectType
    severity: Severity
    priority: float
    action: str
    owner_role: str
    effort: Effort
    estimated_days: float
    evidence: str
    docs: str = ""
    blocks_go_live: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "object_id": self.object_id,
            "object_name": self.object_name,
            "object_type": self.object_type.value,
            "severity": self.severity.value,
            "priority": round(self.priority, 2),
            "action": self.action,
            "owner_role": self.owner_role,
            "effort": self.effort.value,
            "estimated_days": self.estimated_days,
            "blocks_go_live": self.blocks_go_live,
            "evidence": self.evidence,
            "docs": self.docs,
        }


@dataclass
class RemediationBacklog:
    """Ordered remediation plan for a whole assessment run."""

    run_id: str
    items: list[RemediationItem] = field(default_factory=list)

    @property
    def blocking_items(self) -> list[RemediationItem]:
        return [i for i in self.items if i.blocks_go_live]

    @property
    def total_days(self) -> float:
        return round(sum(i.estimated_days for i in self.items), 2)

    def by_owner(self) -> dict[str, list[RemediationItem]]:
        grouped: dict[str, list[RemediationItem]] = {}
        for item in self.items:
            grouped.setdefault(item.owner_role or "Unassigned", []).append(item)
        return grouped

    def top(self, count: int = 10) -> list[RemediationItem]:
        return self.items[:count]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "total_items": len(self.items),
            "blocking_items": len(self.blocking_items),
            "total_estimated_days": self.total_days,
            "items": [i.to_dict() for i in self.items],
        }

    def to_json(self, path: str | None = None, indent: int = 2) -> str:
        payload = json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
        return payload

    def to_csv(self, path: str) -> str:
        columns = [
            "priority", "severity", "blocks_go_live", "object_type", "object_name",
            "rule_id", "title", "action", "owner_role", "effort", "estimated_days", "docs",
        ]
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for item in self.items:
                writer.writerow(item.to_dict())
        return path


def _priority(finding: Finding) -> float:
    severity = SEVERITY_SCORE[finding.severity]
    leverage = OBJECT_LEVERAGE.get(finding.object_type, 1.0)
    effort = EFFORT_FACTOR.get(finding.effort, 1.0)
    return severity * leverage * effort


def _evidence_summary(finding: Finding) -> str:
    refs = [f"{e.source}:{e.reference}" for e in finding.outcome.evidence]
    detail = finding.outcome.detail.strip()
    if refs:
        return f"{detail} [{'; '.join(refs)}]" if detail else "; ".join(refs)
    return detail or "no evidence reference"


def build_backlog(run: AssessmentRun, *, include_partial: bool = True) -> RemediationBacklog:
    """Derive the remediation backlog from every failed (and partial) finding."""
    from fabric_iq.models import RuleStatus

    backlog = RemediationBacklog(run_id=run.run_id)
    wanted = {RuleStatus.FAILED}
    if include_partial:
        wanted.add(RuleStatus.PARTIAL)

    for card in run.scorecards:
        for finding in card.findings:
            if finding.outcome.status not in wanted:
                continue
            backlog.items.append(
                RemediationItem(
                    rule_id=finding.rule_id,
                    title=finding.title,
                    object_id=finding.object_id,
                    object_name=finding.object_name,
                    object_type=finding.object_type,
                    severity=finding.severity,
                    priority=_priority(finding),
                    action=finding.remediation,
                    owner_role=finding.owner_role or "Unassigned",
                    effort=finding.effort,
                    estimated_days=EFFORT_DAYS.get(finding.effort, 2.0),
                    evidence=_evidence_summary(finding),
                    docs=finding.docs,
                    blocks_go_live=finding.is_blocking,
                )
            )

    backlog.items.sort(key=lambda i: (-i.priority, i.object_type.value, i.rule_id))
    return backlog
