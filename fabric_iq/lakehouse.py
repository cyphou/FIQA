"""Medallion persistence for the readiness Lakehouse.

Bronze holds immutable evidence, Silver the normalized inventory, Gold the
marts consumed by the governance semantic model. The writer emits newline
delimited JSON so it works both locally (stdlib only) and from a Fabric
notebook writing to OneLake paths.

Scheduled Lakehouse retention contract
======================================

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

The library enforcement mechanism now exists. :meth:`LakehouseWriter.write_run`
writes a durable per-run manifest as partitions succeed, and
:meth:`LakehouseRetentionPruner.prune` applies the layer-specific cutoffs to
those declared NDJSON partitions. Missing, malformed, or incomplete manifests
produce explicit retention failures and never authorize deletion. The pruner
is deliberately separate from every normal write method and runs only when an
operator or deployment invokes it.

Wiring that explicit entry point into a recurring Fabric deployment schedule,
including the deployment's Delta housekeeping boundary, remains an open
deployment step. This module provides and tests the enforcement mechanism; it
does not claim that a live scheduled retention cycle has run.

"Append, never overwrite" therefore applies only to unexpired historical
partitions: a new ``run_id`` adds a snapshot and an idempotent re-run may
replace its own same-``run_id`` partition. Retention deletion is the explicit
lifecycle boundary, not a rewrite of a prior retained run. This reconciliation
must remain explicit as deployment wiring is added; describing history as
retained forever would contradict this contract.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from fabric_iq.errors import PersistenceError
from fabric_iq.models import AssessmentRun, ReadinessStatus, utcnow
from fabric_iq.remediation import RemediationBacklog, RemediationItem, build_backlog
from fabric_iq.trends import compare_runs

BRONZE = "bronze"
SILVER = "silver"
GOLD = "gold"
MANIFESTS = "manifests"

RETENTION_DAYS = {
    BRONZE: 90,
    SILVER: 180,
    GOLD: 730,
}

_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _stat_has_reparse_point(path_stat: os.stat_result) -> bool:
    return bool(getattr(path_stat, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _path_is_junction(path: str) -> bool:
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def _is_under_root(root_realpath: str, candidate_path: str) -> bool:
    try:
        common = os.path.commonpath([root_realpath, candidate_path])
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(root_realpath)


def _safe_existing_path(
    path: str,
    kind: str,
    *,
    root_realpath: str | None = None,
    required_type: str | None = None,
) -> tuple[os.stat_result | None, str]:
    try:
        path_stat = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        return None, f"cannot inspect {kind}: {exc}"

    if stat.S_ISLNK(path_stat.st_mode) or _stat_has_reparse_point(path_stat):
        return None, f"{kind} is a reparse point"
    try:
        if _path_is_junction(path):
            return None, f"{kind} is a reparse point"
    except OSError as exc:
        return None, f"cannot inspect {kind}: {exc}"

    if root_realpath is not None:
        candidate_realpath = os.path.realpath(path)
        if not _is_under_root(root_realpath, candidate_realpath):
            return None, f"{kind} escapes lakehouse root"

    if required_type == "directory" and not stat.S_ISDIR(path_stat.st_mode):
        return None, f"{kind} is not a directory"
    if required_type == "file" and not stat.S_ISREG(path_stat.st_mode):
        return None, f"{kind} is not a regular file"
    return path_stat, ""


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key: {key}")
        seen.add(key)
        result[key] = value
    return result


def _safe_manifest_table_segment(value: str) -> bool:
    return value not in {"", ".", ".."} and "/" not in value and "\\" not in value


def _dir_fd_deletion_supported() -> bool:
    supports_dir_fd = getattr(os, "supports_dir_fd", frozenset())
    return (
        hasattr(os, "O_DIRECTORY")
        and os.stat in supports_dir_fd
        and os.unlink in supports_dir_fd
    )

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


@dataclass(frozen=True)
class RetentionPartition:
    """A manifest-backed partition classified by a retention run."""

    layer: str
    table: str
    run_id: str
    path: str
    retention_timestamp: str
    cutoff: str


@dataclass(frozen=True)
class RetentionFailure:
    """A partition the pruner could not safely classify or delete."""

    layer: str
    table: str
    run_id: str
    path: str
    reason: str


@dataclass
class RetentionPruneResult:
    """Structured outcome of one explicitly invoked retention pass."""

    pruned: list[RetentionPartition] = field(default_factory=list)
    kept: list[RetentionPartition] = field(default_factory=list)
    failures: list[RetentionFailure] = field(default_factory=list)


@dataclass(frozen=True)
class _RunManifest:
    retention_timestamp: str
    retained_from: datetime
    partitions: frozenset[tuple[str, str, str]]


@dataclass(frozen=True)
class LakehouseRetentionPruner:
    """Delete expired manifest-backed NDJSON partitions under ``root``.

    This capability is intentionally independent from :class:`LakehouseWriter`.
    A deployment or operator must invoke :meth:`prune` explicitly.
    """

    root: str
    now: datetime

    def __post_init__(self) -> None:
        if not self.root:
            raise PersistenceError("lakehouse root is required for retention")
        if not isinstance(self.now, datetime):
            raise PersistenceError("retention now must be a datetime")
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise PersistenceError("retention now must include a timezone")

    def prune(self) -> RetentionPruneResult:
        """Apply each layer's cutoff and return every disposition and failure."""

        if not os.path.lexists(self.root):
            raise PersistenceError(f"lakehouse root does not exist: {self.root}")
        _, root_failure = _safe_existing_path(
            self.root,
            "lakehouse root",
            required_type="directory",
        )
        if root_failure:
            raise PersistenceError(root_failure)
        root_realpath = os.path.realpath(self.root)

        result = RetentionPruneResult()
        manifests: dict[str, tuple[_RunManifest | None, str]] = {}
        now = self.now.astimezone(timezone.utc)

        for layer, retention_days in RETENTION_DAYS.items():
            cutoff = now - timedelta(days=retention_days)
            layer_path = os.path.join(self.root, layer)
            if not os.path.lexists(layer_path):
                continue
            _, layer_failure = _safe_existing_path(
                layer_path,
                "layer path",
                root_realpath=root_realpath,
                required_type="directory",
            )
            if layer_failure:
                result.failures.append(RetentionFailure(layer, "", "", layer_path, layer_failure))
                continue

            try:
                tables = sorted(os.scandir(layer_path), key=lambda entry: entry.name)
            except OSError as exc:
                result.failures.append(
                    RetentionFailure(layer, "", "", layer_path, f"cannot list layer: {exc}")
                )
                continue

            for table_entry in tables:
                try:
                    table_is_symlink = table_entry.is_symlink()
                except OSError as exc:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table_entry.name,
                            "",
                            table_entry.path,
                            f"cannot inspect table path: {exc}",
                        )
                    )
                    continue
                if table_is_symlink:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table_entry.name,
                            "",
                            table_entry.path,
                            "table path is a reparse point",
                        )
                    )
                    continue

                table_stat, table_failure = _safe_existing_path(
                    table_entry.path,
                    "table path",
                    root_realpath=root_realpath,
                    required_type="directory",
                )
                if table_failure or table_stat is None:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table_entry.name,
                            "",
                            table_entry.path,
                            table_failure or "cannot inspect table path",
                        )
                    )
                    continue
                self._prune_table(
                    result,
                    manifests,
                    layer,
                    table_entry.name,
                    table_entry.path,
                    table_stat,
                    cutoff,
                    root_realpath,
                )

        return result

    def _prune_table(
        self,
        result: RetentionPruneResult,
        manifests: dict[str, tuple[_RunManifest | None, str]],
        layer: str,
        table: str,
        table_path: str,
        table_stat: os.stat_result,
        cutoff: datetime,
        root_realpath: str,
    ) -> None:
        table_fd = -1
        if _dir_fd_deletion_supported():
            try:
                table_fd = os.open(table_path, os.O_RDONLY | os.O_DIRECTORY)
                opened_table_stat = os.fstat(table_fd)
            except OSError as exc:
                if table_fd != -1:
                    os.close(table_fd)
                result.failures.append(
                    RetentionFailure(
                        layer,
                        table,
                        "",
                        table_path,
                        f"cannot open table for anchored deletion: {exc}",
                    )
                )
                return
            if not stat.S_ISDIR(opened_table_stat.st_mode):
                os.close(table_fd)
                result.failures.append(
                    RetentionFailure(layer, table, "", table_path, "table path is not a directory")
                )
                return
            if not _same_file(table_stat, opened_table_stat):
                os.close(table_fd)
                result.failures.append(
                    RetentionFailure(
                        layer,
                        table,
                        "",
                        table_path,
                        "table path changed during retention check",
                    )
                )
                return

        try:
            try:
                partitions = sorted(os.scandir(table_path), key=lambda entry: entry.name)
            except OSError as exc:
                result.failures.append(
                    RetentionFailure(layer, table, "", table_path, f"cannot list table: {exc}")
                )
                return

            for partition_entry in partitions:
                if not partition_entry.name.endswith(".jsonl"):
                    continue
                run_id = partition_entry.name[: -len(".jsonl")]
                try:
                    partition_is_symlink = partition_entry.is_symlink()
                except OSError as exc:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table,
                            run_id,
                            partition_entry.path,
                            f"cannot inspect partition: {exc}",
                        )
                    )
                    continue
                if partition_is_symlink:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table,
                            run_id,
                            partition_entry.path,
                            "partition path is a reparse point",
                        )
                    )
                    continue

                partition_stat, partition_failure = _safe_existing_path(
                    partition_entry.path,
                    "partition path",
                    root_realpath=root_realpath,
                    required_type="file",
                )
                if partition_failure or partition_stat is None or not run_id:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table,
                            run_id,
                            partition_entry.path,
                            partition_failure or "partition path is not a named regular file",
                        )
                    )
                    continue

                if run_id not in manifests:
                    manifests[run_id] = self._load_manifest(run_id, root_realpath)
                manifest, manifest_failure = manifests[run_id]
                if manifest is None:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table,
                            run_id,
                            partition_entry.path,
                            manifest_failure,
                        )
                    )
                    continue

                relative_path = f"{layer}/{table}/{partition_entry.name}"
                if (layer, table, relative_path) not in manifest.partitions:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table,
                            run_id,
                            partition_entry.path,
                            "partition is not declared in its run manifest",
                        )
                    )
                    continue

                disposition = RetentionPartition(
                    layer=layer,
                    table=table,
                    run_id=run_id,
                    path=partition_entry.path,
                    retention_timestamp=manifest.retention_timestamp,
                    cutoff=cutoff.isoformat(),
                )
                if manifest.retained_from >= cutoff:
                    result.kept.append(disposition)
                    continue

                if table_fd != -1:
                    self._delete_partition_with_dir_fd(
                        result,
                        layer,
                        table,
                        table_path,
                        table_stat,
                        table_fd,
                        partition_entry.name,
                        partition_entry.path,
                        partition_stat,
                        disposition,
                    )
                    continue

                delete_stat, delete_failure = _safe_existing_path(
                    partition_entry.path,
                    "partition path",
                    root_realpath=root_realpath,
                    required_type="file",
                )
                if delete_failure or delete_stat is None:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table,
                            run_id,
                            partition_entry.path,
                            delete_failure or "cannot inspect partition before deletion",
                        )
                    )
                    continue
                if not _same_file(partition_stat, delete_stat):
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table,
                            run_id,
                            partition_entry.path,
                            "partition changed during retention check",
                        )
                    )
                    continue

                try:
                    os.remove(partition_entry.path)
                except OSError as exc:
                    result.failures.append(
                        RetentionFailure(
                            layer,
                            table,
                            run_id,
                            partition_entry.path,
                            f"cannot delete expired partition: {exc}",
                        )
                    )
                else:
                    result.pruned.append(disposition)
        finally:
            if table_fd != -1:
                os.close(table_fd)

    def _delete_partition_with_dir_fd(
        self,
        result: RetentionPruneResult,
        layer: str,
        table: str,
        table_path: str,
        table_stat: os.stat_result,
        table_fd: int,
        partition_name: str,
        partition_path: str,
        partition_stat: os.stat_result,
        disposition: RetentionPartition,
    ) -> None:
        try:
            current_table_stat = os.stat(table_path, follow_symlinks=False)
        except OSError as exc:
            result.failures.append(
                RetentionFailure(
                    layer,
                    table,
                    disposition.run_id,
                    table_path,
                    f"cannot inspect table before deletion: {exc}",
                )
            )
            return
        if not stat.S_ISDIR(current_table_stat.st_mode) or not _same_file(
            table_stat, current_table_stat
        ):
            result.failures.append(
                RetentionFailure(
                    layer,
                    table,
                    disposition.run_id,
                    table_path,
                    "table path changed during retention check",
                )
            )
            return

        try:
            delete_stat = os.stat(partition_name, dir_fd=table_fd, follow_symlinks=False)
        except OSError as exc:
            result.failures.append(
                RetentionFailure(
                    layer,
                    table,
                    disposition.run_id,
                    partition_path,
                    f"cannot inspect partition before deletion: {exc}",
                )
            )
            return
        if stat.S_ISLNK(delete_stat.st_mode) or _stat_has_reparse_point(delete_stat):
            result.failures.append(
                RetentionFailure(
                    layer,
                    table,
                    disposition.run_id,
                    partition_path,
                    "partition path is a reparse point",
                )
            )
            return
        if not stat.S_ISREG(delete_stat.st_mode):
            result.failures.append(
                RetentionFailure(
                    layer,
                    table,
                    disposition.run_id,
                    partition_path,
                    "partition path is not a regular file",
                )
            )
            return
        if not _same_file(partition_stat, delete_stat):
            result.failures.append(
                RetentionFailure(
                    layer,
                    table,
                    disposition.run_id,
                    partition_path,
                    "partition changed during retention check",
                )
            )
            return

        try:
            os.remove(partition_name, dir_fd=table_fd)
        except OSError as exc:
            result.failures.append(
                RetentionFailure(
                    layer,
                    table,
                    disposition.run_id,
                    partition_path,
                    f"cannot delete expired partition: {exc}",
                )
            )
        else:
            result.pruned.append(disposition)

    def _load_manifest(self, run_id: str, root_realpath: str) -> tuple[_RunManifest | None, str]:
        directory = os.path.join(self.root, MANIFESTS)
        path = os.path.join(directory, f"{run_id}.json")
        if not os.path.lexists(directory):
            return None, f"run manifest is missing: {path}"
        _, directory_failure = _safe_existing_path(
            directory,
            "run manifest directory",
            root_realpath=root_realpath,
            required_type="directory",
        )
        if directory_failure:
            return None, f"{directory_failure}: {directory}"
        if not os.path.lexists(path):
            return None, f"run manifest is missing: {path}"

        manifest_stat, manifest_failure = _safe_existing_path(
            path,
            "run manifest",
            root_realpath=root_realpath,
            required_type="file",
        )
        if manifest_failure or manifest_stat is None:
            return None, f"{manifest_failure or 'cannot inspect run manifest'}: {path}"

        flags = os.O_RDONLY
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if nofollow:
            flags |= nofollow
        fd = -1
        try:
            fd = os.open(path, flags)
            opened_stat = os.fstat(fd)
            if not stat.S_ISREG(opened_stat.st_mode):
                return None, f"run manifest is not a regular file: {path}"
            if not _same_file(manifest_stat, opened_stat):
                return None, f"run manifest changed during open: {path}"
            with os.fdopen(fd, encoding="utf-8") as handle:
                fd = -1
                data = json.load(handle, object_pairs_hook=_reject_duplicate_json_keys)
        except FileNotFoundError:
            return None, f"run manifest is missing: {path}"
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            return None, f"cannot read run manifest {path}: {exc}"
        finally:
            if fd != -1:
                os.close(fd)

        if not isinstance(data, dict):
            return None, f"run manifest is not an object: {path}"
        schema_version = data.get("schema_version")
        if type(schema_version) is not int or schema_version != 1:
            return None, f"run manifest has an unsupported schema version: {path}"
        if data.get("run_id") != run_id:
            return None, f"run manifest does not match partition run_id {run_id}: {path}"

        timestamp = data.get("retention_timestamp")
        if not isinstance(timestamp, str) or not timestamp.strip():
            return None, f"run manifest has no retention_timestamp: {path}"
        try:
            retained_from = datetime.fromisoformat(timestamp)
        except ValueError:
            return None, f"run manifest has an invalid retention_timestamp {timestamp!r}: {path}"
        if retained_from.tzinfo is None or retained_from.utcoffset() is None:
            return None, f"run manifest retention_timestamp has no timezone: {path}"
        retained_from = retained_from.astimezone(timezone.utc)

        partition_rows = data.get("partitions")
        if not isinstance(partition_rows, list):
            return None, f"run manifest partitions are not a list: {path}"
        declared: set[tuple[str, str, str]] = set()
        for index, row in enumerate(partition_rows):
            if not isinstance(row, dict):
                return None, f"run manifest partition {index} is not an object: {path}"
            declared_layer = row.get("layer")
            declared_table = row.get("table")
            declared_path = row.get("path")
            if not all(
                isinstance(value, str) and value
                for value in (declared_layer, declared_table, declared_path)
            ):
                return None, f"run manifest partition {index} is incomplete: {path}"
            if declared_layer not in RETENTION_DAYS:
                return None, f"run manifest partition {index} has an unknown layer: {path}"
            if not _safe_manifest_table_segment(declared_table):
                return None, f"run manifest partition {index} has an unsafe table: {path}"
            expected_path = f"{declared_layer}/{declared_table}/{run_id}.jsonl"
            if declared_path != expected_path:
                return None, f"run manifest partition {index} path does not match its declaration: {path}"
            declared.add((declared_layer, declared_table, declared_path))

        return _RunManifest(timestamp, retained_from, frozenset(declared)), ""


@dataclass
class LakehouseWriter:
    """Write a run into the medallion layout under ``root``.

    ``root`` is a local folder during development and a OneLake ``Files/``
    path when executed from a Fabric notebook.
    """

    root: str
    run_id: str
    _active_manifest: dict[str, Any] | None = field(default=None, init=False, repr=False)

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
        """Persist every layer for one run and durably record its partitions."""
        if self._active_manifest is not None:
            raise PersistenceError("write_run is already active for this writer")

        written_at = utcnow()
        completed_at = str(run.completed_at or "").strip()
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "run_id": self.run_id,
            "completed_at": completed_at,
            "written_at": written_at,
            "retention_timestamp": completed_at or written_at,
            "partitions": [],
        }
        written: dict[str, Any] = {"run_id": self.run_id, "written_at": written_at}
        self._active_manifest = manifest
        try:
            written["manifest"] = self._write_manifest(manifest)
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
        finally:
            self._active_manifest = None
        return written

    # ── io ────────────────────────────────────────────────────────

    def _write_manifest(self, manifest: dict[str, Any]) -> str:
        directory = os.path.join(self.root, MANIFESTS)
        path = os.path.join(directory, f"{self.run_id}.json")
        temporary_path = f"{path}.tmp"
        try:
            os.makedirs(directory, exist_ok=True)
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            os.replace(temporary_path, path)
        except OSError as exc:
            raise PersistenceError(f"cannot write run manifest {path}: {exc}") from exc
        return path

    def _record_manifest_partition(self, layer: str, table: str) -> None:
        if self._active_manifest is None:
            return
        partition = {
            "layer": layer,
            "table": table,
            "path": f"{layer}/{table}/{self.run_id}.jsonl",
        }
        partitions = self._active_manifest["partitions"]
        if partition not in partitions:
            partitions.append(partition)
        self._write_manifest(self._active_manifest)

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
        self._record_manifest_partition(layer, table)
        return path
