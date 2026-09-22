"""Medallion persistence for the readiness Lakehouse.

Bronze holds immutable evidence, Silver the normalized inventory, Gold the
marts consumed by the governance semantic model. The writer emits newline
delimited JSON so it works both locally (stdlib only) and from a Fabric
notebook writing to OneLake paths.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterable

from fabric_iq.errors import PersistenceError
from fabric_iq.models import AssessmentRun, ReadinessStatus, utcnow
from fabric_iq.remediation import RemediationBacklog

BRONZE = "bronze"
SILVER = "silver"
GOLD = "gold"

#: Gold marts produced by a run.
GOLD_TABLES = (
    "MartTenantReadiness",
    "MartWorkspaceReadiness",
    "MartObjectReadiness",
    "MartBlockingFindings",
    "MartRemediationBacklog",
    "MartCoverageAndFreshness",
)


def _json_scalar(value: Any) -> str:
    """Serialize a nested value (dict/list) into a single scalar JSON string.

    DirectLake (and Delta in general, once a semantic model reads it through
    the SQL analytics endpoint) only supports scalar column types -- no maps,
    arrays or structs. Every Gold mart row must therefore be flat: any field
    that is naturally a dict or a list is serialized here instead of being
    written as-is, so the JSON Spark infers from these NDJSON files -- and the
    Delta table it writes -- stays scalar-only.
    """
    return json.dumps(value, ensure_ascii=False, default=str)


# --------------------------------------------------------------------------
# Gold mart row builders (module-level, scalar-only, shared with reports)
# --------------------------------------------------------------------------
#
# These are plain functions -- not methods -- so both :class:`LakehouseWriter`
# and the Power BI report generator (:mod:`fabric_iq.powerbi`) build the exact
# same rows from the exact same code path: there is a single definition of
# what a Gold mart row looks like.


def _base_row(run_id: str, card) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "object_id": card.object_id,
        "object_name": card.object_name,
        "object_type": card.object_type.value,
        "parent_id": card.parent_id,
        "score": round(card.score, 2),
        "raw_score": round(card.raw_score, 2),
        "status": card.status.value,
        "eligible": card.eligible,
        "confidence": round(card.confidence, 4),
        "coverage": round(card.coverage, 4),
        "blocking_findings": len(card.blocking_findings),
        "failed_findings": len(card.failed_findings),
        "ruleset_version": card.ruleset_version,
        "assessed_at": card.assessed_at,
    }


def tenant_mart_rows(run: AssessmentRun, run_id: str = "") -> list[dict[str, Any]]:
    from fabric_iq.models import ObjectType

    return [
        {
            **_base_row(run_id, c),
            "dimension_scores_json": _json_scalar(c.dimension_scores),
            "notes_json": _json_scalar(c.notes),
        }
        for c in run.by_type(ObjectType.TENANT)
    ]


def workspace_mart_rows(run: AssessmentRun, run_id: str = "") -> list[dict[str, Any]]:
    from fabric_iq.models import ObjectType

    return [
        {**_base_row(run_id, c), "dimension_scores_json": _json_scalar(c.dimension_scores)}
        for c in run.by_type(ObjectType.WORKSPACE)
    ]


def object_mart_rows(run: AssessmentRun, run_id: str = "") -> list[dict[str, Any]]:
    from fabric_iq.models import ObjectType

    leaf_types = (ObjectType.SEMANTIC_MODEL, ObjectType.REPORT, ObjectType.DATA_AGENT)
    return [
        {**_base_row(run_id, c), "dimension_scores_json": _json_scalar(c.dimension_scores)}
        for c in run.scorecards
        if c.object_type in leaf_types
    ]


def blocking_mart_rows(run: AssessmentRun, run_id: str = "") -> list[dict[str, Any]]:
    rows = []
    for finding in run.blocking_findings:
        outcome = finding.outcome
        rows.append(
            {
                "run_id": run_id,
                "rule_id": finding.rule_id,
                "title": finding.title,
                "object_id": finding.object_id,
                "object_name": finding.object_name,
                "object_type": finding.object_type.value,
                "dimension": finding.dimension.value,
                "severity": finding.severity.value,
                "remediation": finding.remediation,
                "effort": finding.effort.value,
                "owner_role": finding.owner_role or "Unassigned",
                "docs": finding.docs,
                "outcome_status": outcome.status.value,
                "outcome_score": round(outcome.score, 4),
                "outcome_detail": outcome.detail,
                "outcome_observed_json": _json_scalar(outcome.observed),
                "outcome_evidence_json": _json_scalar([e.to_dict() for e in outcome.evidence]),
            }
        )
    return rows


def coverage_mart_rows(run: AssessmentRun, run_id: str = "") -> list[dict[str, Any]]:
    rows = []
    for card in run.scorecards:
        unevaluated = [f.rule_id for f in card.findings if f.outcome.status.value == "not_evaluated"]
        rows.append(
            {
                "run_id": run_id,
                "object_id": card.object_id,
                "object_type": card.object_type.value,
                "coverage": round(card.coverage, 4),
                "confidence": round(card.confidence, 4),
                "not_evaluated_count": len(unevaluated),
                "not_evaluated_rules_json": _json_scalar(unevaluated),
                "is_published": card.status is not ReadinessStatus.NOT_EVALUATED,
                "assessed_at": card.assessed_at,
            }
        )
    return rows


def backlog_mart_rows(backlog: RemediationBacklog, run_id: str = "") -> list[dict[str, Any]]:
    return [{"run_id": run_id, **i.to_dict()} for i in backlog.items]


def gold_mart_rows(
    run: AssessmentRun, backlog: RemediationBacklog, *, run_id: str = ""
) -> dict[str, list[dict[str, Any]]]:
    """Build every Gold mart's rows for one run, keyed by table name.

    Single entry point used by both :meth:`LakehouseWriter.write_gold` (which
    persists these rows as NDJSON) and the Power BI report generator (which
    needs the identical rows to populate a local/offline project).
    """
    return {
        "MartTenantReadiness": tenant_mart_rows(run, run_id),
        "MartWorkspaceReadiness": workspace_mart_rows(run, run_id),
        "MartObjectReadiness": object_mart_rows(run, run_id),
        "MartBlockingFindings": blocking_mart_rows(run, run_id),
        "MartRemediationBacklog": backlog_mart_rows(backlog, run_id),
        "MartCoverageAndFreshness": coverage_mart_rows(run, run_id),
    }


@dataclass
class LakehouseWriter:
    """Write a run into the medallion layout under ``root``.

    ``root`` is a local folder during development and a OneLake ``Files/``
    path when executed from a Fabric notebook.
    """

    root: str
    run_id: str

    def __post_init__(self) -> None:
        if not self.root:
            raise PersistenceError("lakehouse root is required")
        if not self.run_id:
            raise PersistenceError("run_id is required")

    # ── layer writers ─────────────────────────────────────────────

    def write_bronze(self, records: Iterable[Any]) -> str:
        payload = [r.to_dict() if hasattr(r, "to_dict") else r for r in records]
        return self._write_ndjson(BRONZE, "evidence", payload)

    def write_silver(self, inventory: dict[str, Any]) -> list[str]:
        written = []
        for section, rows in inventory.items():
            if section == "tenant":
                rows = [rows]
            if not isinstance(rows, list):
                continue
            written.append(self._write_ndjson(SILVER, section, rows))
        return written

    def write_gold(self, run: AssessmentRun, backlog: RemediationBacklog) -> dict[str, str]:
        marts = gold_mart_rows(run, backlog, run_id=self.run_id)
        return {name: self._write_ndjson(GOLD, name, rows) for name, rows in marts.items()}

    def write_run(
        self,
        run: AssessmentRun,
        backlog: RemediationBacklog,
        *,
        inventory: dict[str, Any] | None = None,
        bronze: Iterable[Any] | None = None,
    ) -> dict[str, Any]:
        """Persist every layer for one run and return the written paths."""
        written: dict[str, Any] = {"run_id": self.run_id, "written_at": utcnow()}
        if bronze is not None:
            written[BRONZE] = self.write_bronze(bronze)
        if inventory is not None:
            written[SILVER] = self.write_silver(inventory)
        written[GOLD] = self.write_gold(run, backlog)
        return written

    # ── io ────────────────────────────────────────────────────────

    def _write_ndjson(self, layer: str, table: str, rows: list[dict[str, Any]]) -> str:
        directory = os.path.join(self.root, layer, table)
        path = os.path.join(directory, f"{self.run_id}.jsonl")
        try:
            os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            raise PersistenceError(f"cannot write {path}: {exc}") from exc
        return path
