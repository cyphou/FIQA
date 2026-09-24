"""Medallion persistence for the readiness Lakehouse.

Bronze holds immutable evidence, Silver the normalized inventory, Gold the
marts consumed by the governance semantic model. The writer emits newline
delimited JSON so it works both locally (stdlib only) and from a Fabric
notebook writing to OneLake paths.

Scheduled Lakehouse retention contract (not yet enforced by this writer)
==========================================================================

An unattended deployment of ``FabricIQReadiness`` must enforce these maximum
retention periods, measured from the completed timestamp of the run that
materialized the partition:

* Bronze raw evidence: 90 days.
* Silver normalized inventory: 180 days.
* Gold readiness marts: 730 days.

Bronze can contain raw API payloads, including tenant-authored metadata and,
when artifact-user collection is enabled, owner UPNs. Silver remains
identifying tenant inventory. Gold is retained longer so compatible runs can
support trend and remediation comparison, but it is not anonymous: its object
names, findings, and nested outcome fields remain tenant data. No layer has an
indefinite default, and expiry means deletion from the active Lakehouse, not an
unapproved archival copy.

The deployment-owned retention job must delete every table partition for an
expired ``run_id`` in the applicable layer and must retain enough durable run
metadata to determine expiry for both completed and failed/partial runs. A
``run_id`` is opaque, so the job must not infer age from its value. If a
partition has no trustworthy lifecycle timestamp, the job must surface a
retention failure for operator action rather than preserve it indefinitely.

This module currently does none of that: :class:`LakehouseWriter` writes each
``run_id`` partition but has no listing, expiry, archival, or deletion method.
Implementing a safe housekeeper requires durable lifecycle metadata and
failure handling across OneLake/Delta and NDJSON, so it is a follow-on
engineering task rather than an implicit side effect of a write.

"Append, never overwrite" therefore applies only to unexpired historical
partitions: a new ``run_id`` adds a snapshot and an idempotent re-run may
replace its own same-``run_id`` partition. Retention deletion is the explicit
lifecycle boundary, not a rewrite of a prior retained run. This reconciliation
must remain explicit if enforcement is added; describing history as retained
forever would contradict this contract.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterable

from fabric_iq.errors import PersistenceError
from fabric_iq.models import AssessmentRun, ReadinessStatus, utcnow
from fabric_iq.remediation import RemediationBacklog, RemediationItem, build_backlog
from fabric_iq.trends import compare_runs

BRONZE = "bronze"
SILVER = "silver"
GOLD = "gold"

#: Gold marts produced by a run.
GOLD_TABLES = (
    "MartRunSummary",
    "MartTenantReadiness",
    "MartWorkspaceReadiness",
    "MartObjectReadiness",
    "MartBlockingFindings",
    "MartRemediationBacklog",
    "MartRemediationBurnDown",
    "MartCoverageAndFreshness",
    "MartRunTrend",
)

#: Explicit column schema for every Gold mart, keyed by table name.
#:
#: A mart can legitimately have zero rows for a given run -- a clean tenant has an
#: empty ``MartBlockingFindings``, a tenant with no scanned objects yet has an empty
#: ``MartObjectReadiness``. Reading an *empty* NDJSON file back with Spark's schema
#: inference yields a DataFrame with **no columns**, and creating a Delta table from
#: that would either fail or produce an unusable table. The notebook uses this
#: dict to build an explicit, typed empty frame instead of skipping the table
#: entirely, so every table in :data:`GOLD_TABLES` always exists after a run --
#: with 0 rows if nothing qualified -- rather than being silently absent and making
#: the Direct Lake report fail with "Invalid object name". Types are the small,
#: Spark-agnostic vocabulary consumed by the notebook: ``string``, ``double``,
#: ``long`` and ``boolean``.
GOLD_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "MartRunSummary": (
        ("run_id", "string"),
        ("tenant_id", "string"),
        ("ruleset_version", "string"),
        ("collector_mode", "string"),
        ("started_at", "string"),
        ("completed_at", "string"),
        ("tenant_count", "long"),
        ("workspace_count", "long"),
        ("semantic_model_count", "long"),
        ("report_count", "long"),
        ("data_agent_count", "long"),
        ("assessed_object_count", "long"),
        ("published_object_count", "long"),
        ("eligible_object_count", "long"),
        ("not_evaluated_object_count", "long"),
        ("blocking_findings_count", "long"),
        ("failed_findings_count", "long"),
        ("backlog_items_count", "long"),
        ("average_object_score", "double"),
        ("average_object_confidence", "double"),
        ("average_object_coverage", "double"),
    ),
    "MartTenantReadiness": (
        ("run_id", "string"),
        ("object_id", "string"),
        ("object_name", "string"),
        ("object_type", "string"),
        ("parent_id", "string"),
        ("score", "double"),
        ("raw_score", "double"),
        ("status", "string"),
        ("eligible", "boolean"),
        ("confidence", "double"),
        ("coverage", "double"),
        ("blocking_findings", "long"),
        ("failed_findings", "long"),
        ("ruleset_version", "string"),
        ("assessed_at", "string"),
        ("dimension_scores_json", "string"),
        ("notes_json", "string"),
    ),
    "MartWorkspaceReadiness": (
        ("run_id", "string"),
        ("object_id", "string"),
        ("object_name", "string"),
        ("object_type", "string"),
        ("parent_id", "string"),
        ("score", "double"),
        ("raw_score", "double"),
        ("status", "string"),
        ("eligible", "boolean"),
        ("confidence", "double"),
        ("coverage", "double"),
        ("blocking_findings", "long"),
        ("failed_findings", "long"),
        ("ruleset_version", "string"),
        ("assessed_at", "string"),
        ("dimension_scores_json", "string"),
    ),
    "MartObjectReadiness": (
        ("run_id", "string"),
        ("object_id", "string"),
        ("object_name", "string"),
        ("object_type", "string"),
        ("parent_id", "string"),
        ("score", "double"),
        ("raw_score", "double"),
        ("status", "string"),
        ("eligible", "boolean"),
        ("confidence", "double"),
        ("coverage", "double"),
        ("blocking_findings", "long"),
        ("failed_findings", "long"),
        ("ruleset_version", "string"),
        ("assessed_at", "string"),
        ("dimension_scores_json", "string"),
    ),
    "MartBlockingFindings": (
        ("run_id", "string"),
        ("rule_id", "string"),
        ("title", "string"),
        ("object_id", "string"),
        ("object_name", "string"),
        ("object_type", "string"),
        ("dimension", "string"),
        ("severity", "string"),
        ("remediation", "string"),
        ("effort", "string"),
        ("owner_role", "string"),
        ("docs", "string"),
        ("outcome_status", "string"),
        ("outcome_score", "double"),
        ("outcome_detail", "string"),
        ("outcome_observed_json", "string"),
        ("outcome_evidence_json", "string"),
    ),
    "MartRemediationBacklog": (
        ("run_id", "string"),
        ("rule_id", "string"),
        ("title", "string"),
        ("object_id", "string"),
        ("object_name", "string"),
        ("object_type", "string"),
        ("severity", "string"),
        ("priority", "double"),
        ("action", "string"),
        ("owner_role", "string"),
        ("effort", "string"),
        ("estimated_days", "double"),
        ("blocks_go_live", "boolean"),
        ("evidence", "string"),
        ("docs", "string"),
    ),
    "MartRemediationBurnDown": (
        ("run_id", "string"),
        ("baseline_run_id", "string"),
        ("current_run_id", "string"),
        ("previous_seen_run_id", "string"),
        ("rule_id", "string"),
        ("title", "string"),
        ("object_id", "string"),
        ("object_name", "string"),
        ("object_type", "string"),
        ("owner_role", "string"),
        ("severity", "string"),
        ("effort", "string"),
        ("estimated_days", "double"),
        ("priority", "double"),
        ("blocks_go_live", "boolean"),
        ("lifecycle_status", "string"),
        ("priority_delta", "double"),
        ("estimated_days_delta", "double"),
        ("detail", "string"),
    ),
    "MartCoverageAndFreshness": (
        ("run_id", "string"),
        ("object_id", "string"),
        ("object_type", "string"),
        ("coverage", "double"),
        ("confidence", "double"),
        ("not_evaluated_count", "long"),
        ("not_evaluated_rules_json", "string"),
        ("is_published", "boolean"),
        ("assessed_at", "string"),
    ),
    "MartRunTrend": (
        ("run_id", "string"),
        ("baseline_run_id", "string"),
        ("current_run_id", "string"),
        ("ruleset_version_changed", "boolean"),
        ("object_id", "string"),
        ("object_name", "string"),
        ("object_type", "string"),
        ("classification", "string"),
        ("score_delta", "double"),
        ("confidence_delta", "double"),
        ("coverage_delta", "double"),
        ("baseline_score", "double"),
        ("current_score", "double"),
        ("baseline_coverage", "double"),
        ("current_coverage", "double"),
        ("baseline_confidence", "double"),
        ("current_confidence", "double"),
        ("detail", "string"),
    ),
}


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


def _backlog_item_key(item: RemediationItem) -> tuple[str, str]:
    return (item.rule_id, item.object_id)


def _backlog_items_by_key(backlog: RemediationBacklog) -> dict[tuple[str, str], RemediationItem]:
    return {_backlog_item_key(item): item for item in backlog.items}


def _latest_backlog_items_by_key(
    history: Iterable[tuple[AssessmentRun, RemediationBacklog]],
) -> dict[tuple[str, str], tuple[str, RemediationItem]]:
    latest: dict[tuple[str, str], tuple[str, RemediationItem]] = {}
    for run, backlog in history:
        for item in backlog.items:
            latest[_backlog_item_key(item)] = (run.run_id, item)
    return latest


def _burndown_row(
    *,
    run_id: str,
    baseline_run_id: str,
    current_run_id: str,
    previous_seen_run_id: str,
    item: RemediationItem,
    lifecycle_status: str,
    priority_delta: float = 0.0,
    estimated_days_delta: float = 0.0,
    detail: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "current_run_id": current_run_id,
        "previous_seen_run_id": previous_seen_run_id,
        "rule_id": item.rule_id,
        "title": item.title,
        "object_id": item.object_id,
        "object_name": item.object_name,
        "object_type": item.object_type.value,
        "owner_role": item.owner_role,
        "severity": item.severity.value,
        "effort": item.effort.value,
        "estimated_days": item.estimated_days,
        "priority": round(item.priority, 2),
        "blocks_go_live": item.blocks_go_live,
        "lifecycle_status": lifecycle_status,
        "priority_delta": round(priority_delta, 2),
        "estimated_days_delta": round(estimated_days_delta, 2),
        "detail": detail,
    }


def remediation_burndown_mart_rows(
    history_runs: Iterable[AssessmentRun] | None,
    current_run: AssessmentRun,
    current_backlog: RemediationBacklog,
    run_id: str = "",
) -> list[dict[str, Any]]:
    """Build backlog lifecycle rows for the current run.

    A backlog item is matched by the stable pair ``(rule_id, object_id)``. The
    latest comparable historical run is the baseline for open/resolved status;
    older comparable runs are used only to distinguish a genuinely new item
    from one that was previously resolved and has now reopened.
    """

    history = [(run, build_backlog(run)) for run in history_runs or []]
    latest_history = history[-1] if history else None
    baseline_run_id = latest_history[0].run_id if latest_history else ""
    baseline_items = _backlog_items_by_key(latest_history[1]) if latest_history else {}
    latest_seen = _latest_backlog_items_by_key(history)
    current_items = _backlog_items_by_key(current_backlog)

    rows: list[dict[str, Any]] = []
    for key, current_item in current_items.items():
        if key in baseline_items:
            baseline_item = baseline_items[key]
            priority_delta = current_item.priority - baseline_item.priority
            days_delta = current_item.estimated_days - baseline_item.estimated_days
            if round(priority_delta, 2) != 0 or round(days_delta, 2) != 0:
                status = "changed_priority"
                detail = "Backlog item persists, but priority or estimated effort changed."
            else:
                status = "open"
                detail = "Backlog item remains open from the baseline run."
            previous_seen_run_id = baseline_run_id
        elif key in latest_seen:
            previous_seen_run_id, previous_item = latest_seen[key]
            priority_delta = current_item.priority - previous_item.priority
            days_delta = current_item.estimated_days - previous_item.estimated_days
            status = "reopened"
            detail = "Backlog item was absent from the baseline run but appeared in earlier history."
        else:
            previous_seen_run_id = ""
            priority_delta = current_item.priority
            days_delta = current_item.estimated_days
            status = "new"
            detail = "Backlog item is new in the current run."
        rows.append(
            _burndown_row(
                run_id=run_id,
                baseline_run_id=baseline_run_id,
                current_run_id=current_run.run_id,
                previous_seen_run_id=previous_seen_run_id,
                item=current_item,
                lifecycle_status=status,
                priority_delta=priority_delta,
                estimated_days_delta=days_delta,
                detail=detail,
            )
        )

    for key, baseline_item in baseline_items.items():
        if key in current_items:
            continue
        rows.append(
            _burndown_row(
                run_id=run_id,
                baseline_run_id=baseline_run_id,
                current_run_id=current_run.run_id,
                previous_seen_run_id=baseline_run_id,
                item=baseline_item,
                lifecycle_status="resolved",
                priority_delta=-baseline_item.priority,
                estimated_days_delta=-baseline_item.estimated_days,
                detail="Backlog item was present in the baseline run and is no longer present.",
            )
        )

    rows.sort(key=lambda row: (row["lifecycle_status"], row["object_type"], row["rule_id"], row["object_id"]))
    return rows


def _average(values: Iterable[float]) -> float:
    numbers = list(values)
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 4)


def run_summary_mart_rows(
    run: AssessmentRun, backlog: RemediationBacklog, run_id: str = ""
) -> list[dict[str, Any]]:
    from fabric_iq.models import ObjectType

    leaf_types = (ObjectType.SEMANTIC_MODEL, ObjectType.REPORT, ObjectType.DATA_AGENT)
    leaf_cards = [c for c in run.scorecards if c.object_type in leaf_types]
    published_cards = [c for c in leaf_cards if c.status is not ReadinessStatus.NOT_EVALUATED]
    return [
        {
            "run_id": run_id,
            "tenant_id": run.tenant_id,
            "ruleset_version": run.ruleset_version,
            "collector_mode": run.collector_mode,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "tenant_count": len(run.by_type(ObjectType.TENANT)),
            "workspace_count": len(run.by_type(ObjectType.WORKSPACE)),
            "semantic_model_count": len(run.by_type(ObjectType.SEMANTIC_MODEL)),
            "report_count": len(run.by_type(ObjectType.REPORT)),
            "data_agent_count": len(run.by_type(ObjectType.DATA_AGENT)),
            "assessed_object_count": len(leaf_cards),
            "published_object_count": len(published_cards),
            "eligible_object_count": sum(1 for c in leaf_cards if c.eligible),
            "not_evaluated_object_count": sum(1 for c in leaf_cards if c.status is ReadinessStatus.NOT_EVALUATED),
            "blocking_findings_count": len(run.blocking_findings),
            "failed_findings_count": sum(len(c.failed_findings) for c in run.scorecards),
            "backlog_items_count": len(backlog.items),
            "average_object_score": _average(c.score for c in published_cards),
            "average_object_confidence": _average(c.confidence for c in leaf_cards),
            "average_object_coverage": _average(c.coverage for c in leaf_cards),
        }
    ]


def run_trend_mart_rows(
    baseline: AssessmentRun | None,
    current: AssessmentRun,
    run_id: str = "",
) -> list[dict[str, Any]]:
    """Build run-to-run trend rows for the current assessment run."""

    if baseline is None:
        return []
    report = compare_runs(baseline, current)
    rows = []
    for finding in report.findings:
        row = finding.to_dict()
        row["run_id"] = run_id
        row["ruleset_version_changed"] = report.ruleset_version_changed
        rows.append(row)
    return rows


def load_assessment_run(path: str) -> AssessmentRun:
    """Load an assessment run persisted by ``AssessmentRun.to_json``."""

    try:
        return AssessmentRun.from_json(path)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise PersistenceError(f"cannot load assessment run {path}: {exc}") from exc


def select_latest_baseline_run(
    reports_dir: str,
    current_run: AssessmentRun,
    *,
    same_ruleset_only: bool = True,
) -> AssessmentRun | None:
    """Return the latest previous comparable assessment run from ``reports_dir``.

    The deployed notebook writes durable run JSON files under
    ``Files/readiness/reports``. This helper uses that medallion history as the
    source of truth for trend comparisons, excluding the current run and, by
    default, ignoring runs created with a different ruleset version.
    """

    candidates = select_comparable_history_runs(
        reports_dir, current_run, same_ruleset_only=same_ruleset_only
    )
    if not candidates:
        return None
    return candidates[-1]


def select_comparable_history_runs(
    reports_dir: str,
    current_run: AssessmentRun,
    *,
    same_ruleset_only: bool = True,
) -> list[AssessmentRun]:
    """Return previous comparable runs from ``reports_dir``, oldest first."""

    if not reports_dir:
        raise PersistenceError("reports_dir is required for history selection")
    if not current_run.run_id:
        raise PersistenceError("current_run.run_id is required for history selection")
    if not os.path.isdir(reports_dir):
        return []

    candidates: list[AssessmentRun] = []
    for name in sorted(os.listdir(reports_dir)):
        if not name.endswith("_assessment.json"):
            continue
        path = os.path.join(reports_dir, name)
        baseline = load_assessment_run(path)
        if baseline.run_id == current_run.run_id:
            continue
        if baseline.tenant_id != current_run.tenant_id:
            continue
        if same_ruleset_only and baseline.ruleset_version != current_run.ruleset_version:
            continue
        candidates.append(baseline)
    return sorted(candidates, key=_baseline_sort_key)


def _baseline_sort_key(run: AssessmentRun) -> tuple[str, str, str]:
    return (run.completed_at or "", run.started_at or "", run.run_id)


def gold_mart_rows(
    run: AssessmentRun,
    backlog: RemediationBacklog,
    *,
    run_id: str = "",
    baseline_run: AssessmentRun | None = None,
    history_runs: Iterable[AssessmentRun] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build every Gold mart's rows for one run, keyed by table name.

    Single entry point used by both :meth:`LakehouseWriter.write_gold` (which
    persists these rows as NDJSON) and the Power BI report generator (which
    needs the identical rows to populate a local/offline project).
    """
    return {
        "MartRunSummary": run_summary_mart_rows(run, backlog, run_id),
        "MartTenantReadiness": tenant_mart_rows(run, run_id),
        "MartWorkspaceReadiness": workspace_mart_rows(run, run_id),
        "MartObjectReadiness": object_mart_rows(run, run_id),
        "MartBlockingFindings": blocking_mart_rows(run, run_id),
        "MartRemediationBacklog": backlog_mart_rows(backlog, run_id),
        "MartRemediationBurnDown": remediation_burndown_mart_rows(
            history_runs if history_runs is not None else ([baseline_run] if baseline_run else []),
            run,
            backlog,
            run_id,
        ),
        "MartCoverageAndFreshness": coverage_mart_rows(run, run_id),
        "MartRunTrend": run_trend_mart_rows(baseline_run, run, run_id),
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

    def write_gold(
        self,
        run: AssessmentRun,
        backlog: RemediationBacklog,
        *,
        baseline_run: AssessmentRun | None = None,
        history_runs: Iterable[AssessmentRun] | None = None,
    ) -> dict[str, str]:
        marts = gold_mart_rows(
            run,
            backlog,
            run_id=self.run_id,
            baseline_run=baseline_run,
            history_runs=history_runs,
        )
        return {name: self._write_ndjson(GOLD, name, rows) for name, rows in marts.items()}

    def write_run(
        self,
        run: AssessmentRun,
        backlog: RemediationBacklog,
        *,
        inventory: dict[str, Any] | None = None,
        bronze: Iterable[Any] | None = None,
        baseline_run: AssessmentRun | None = None,
        history_runs: Iterable[AssessmentRun] | None = None,
    ) -> dict[str, Any]:
        """Persist every layer for one run and return the written paths."""
        written: dict[str, Any] = {"run_id": self.run_id, "written_at": utcnow()}
        if bronze is not None:
            written[BRONZE] = self.write_bronze(bronze)
        if inventory is not None:
            written[SILVER] = self.write_silver(inventory)
        written[GOLD] = self.write_gold(
            run,
            backlog,
            baseline_run=baseline_run,
            history_runs=history_runs,
        )
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
