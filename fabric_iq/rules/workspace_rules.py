"""Workspace-level readiness rules.

A workspace is the security and lifecycle boundary of Fabric IQ content. These
rules judge ownership, privilege hygiene, capacity binding and operability.
"""

from __future__ import annotations

from fabric_iq.models import Dimension, Effort, ObjectType, RuleOutcome, Severity
from fabric_iq.rules.base import evidence, graded, ratio, registry, require
from fabric_iq.rules.tenant_rules import _sku_is_eligible

W = ObjectType.WORKSPACE
DOCS_ROLES = "https://learn.microsoft.com/fabric/fundamentals/roles-workspaces"

#: Roles that grant write access and therefore require justification.
PRIVILEGED_ROLES = ("Admin", "Member", "Contributor")

#: Workspaces older than this without activity are treated as dormant.
DORMANCY_DAYS = 90


@registry.add(
    "WKS-001",
    "Workspace runs on a Copilot-eligible capacity",
    W,
    Dimension.ARCHITECTURE,
    Severity.BLOCKING,
    "Reassign the workspace to a Fabric F2+ or Premium P1+ capacity.",
    weight=2.0,
    effort=Effort.S,
    owner_role="Capacity Administrator",
)
def workspace_capacity(subject: dict) -> RuleOutcome:
    gap = require(subject, "capacity_sku")
    if gap:
        return gap
    sku = subject["capacity_sku"]
    if _sku_is_eligible(sku):
        return RuleOutcome.passed(
            f"workspace runs on {sku}",
            observed={"sku": sku},
            evidence=evidence("fabric_rest", "workspace.capacityId"),
        )
    return RuleOutcome.failed(
        f"capacity SKU {sku or 'none'} cannot host Copilot or Data Agent workloads",
        observed={"sku": sku},
        evidence=evidence("fabric_rest", "workspace.capacityId"),
    )


@registry.add(
    "WKS-002",
    "Workspace has an accountable owner",
    W,
    Dimension.GOVERNANCE,
    Severity.BLOCKING,
    "Assign a named business owner and a technical contact to the workspace.",
    weight=1.5,
    effort=Effort.XS,
    owner_role="Workspace Admin",
)
def workspace_owner(subject: dict) -> RuleOutcome:
    gap = require(subject, "business_owner", "technical_owner")
    if gap:
        return gap
    present = [k for k in ("business_owner", "technical_owner") if subject.get(k)]
    if len(present) == 2:
        return RuleOutcome.passed(
            "business and technical owners are recorded",
            evidence=evidence("governance_register", "workspace.owners"),
        )
    if present:
        return RuleOutcome.partial(
            0.5,
            f"only {present[0]} is recorded",
            evidence=evidence("governance_register", "workspace.owners"),
        )
    return RuleOutcome.failed(
        "no accountable owner is recorded for this workspace",
        evidence=evidence("governance_register", "workspace.owners"),
    )


@registry.add(
    "WKS-003",
    "Privileged access is granted through Entra groups, not individuals",
    W,
    Dimension.SECURITY,
    Severity.MAJOR,
    "Replace individual Admin/Member/Contributor assignments with Entra security groups.",
    weight=1.5,
    effort=Effort.M,
    owner_role="Workspace Admin",
    docs=DOCS_ROLES,
)
def group_based_access(subject: dict) -> RuleOutcome:
    gap = require(subject, "role_assignments")
    if gap:
        return gap
    assignments = subject["role_assignments"]
    privileged = [a for a in assignments if a.get("role") in PRIVILEGED_ROLES]
    if not privileged:
        return RuleOutcome.not_applicable("no privileged assignment on this workspace")
    group_based = [a for a in privileged if a.get("principal_type") == "Group"]
    individuals = [a.get("principal", "?") for a in privileged if a.get("principal_type") != "Group"]
    return graded(
        ratio(len(group_based), len(privileged)),
        f"{len(group_based)}/{len(privileged)} privileged assignments are group-based",
        pass_at=1.0,
        observed={"individual_principals": len(individuals)},
        ev=evidence("scanner_api", "workspace.users"),
    )


@registry.add(
    "WKS-004",
    "Privileged access is not excessive",
    W,
    Dimension.SECURITY,
    Severity.MAJOR,
    "Reduce Admin and Member assignments to the minimum; move consumers to Viewer.",
    effort=Effort.M,
    owner_role="Workspace Admin",
    docs=DOCS_ROLES,
)
def least_privilege(subject: dict) -> RuleOutcome:
    gap = require(subject, "role_assignments")
    if gap:
        return gap
    assignments = subject["role_assignments"]
    if not assignments:
        return RuleOutcome.not_evaluated("no role assignment returned for this workspace")
    admins = [a for a in assignments if a.get("role") == "Admin"]
    members = [a for a in assignments if a.get("role") == "Member"]
    excessive = len(admins) > 3 or ratio(len(admins) + len(members), len(assignments)) > 0.5
    detail = f"{len(admins)} admins, {len(members)} members, {len(assignments)} total assignments"
    if excessive:
        return RuleOutcome.failed(
            detail,
            observed={"admins": len(admins), "members": len(members)},
            evidence=evidence("scanner_api", "workspace.users"),
        )
    return RuleOutcome.passed(
        detail,
        observed={"admins": len(admins), "members": len(members)},
        evidence=evidence("scanner_api", "workspace.users"),
    )


@registry.add(
    "WKS-005",
    "Workspace lifecycle stage is declared",
    W,
    Dimension.GOVERNANCE,
    Severity.MINOR,
    "Tag the workspace as Dev, Test or Prod and keep production content separated from development content.",
    effort=Effort.XS,
    owner_role="Workspace Admin",
)
def lifecycle_stage(subject: dict) -> RuleOutcome:
    gap = require(subject, "lifecycle_stage")
    if gap:
        return gap
    stage = (subject["lifecycle_stage"] or "").strip().lower()
    if stage in ("dev", "test", "prod", "production", "development"):
        return RuleOutcome.passed(
            f"lifecycle stage is '{stage}'",
            evidence=evidence("governance_register", "workspace.lifecycle_stage"),
        )
    return RuleOutcome.failed(
        "workspace lifecycle stage is undeclared; Dev and Prod content may be mixed",
        evidence=evidence("governance_register", "workspace.lifecycle_stage"),
    )


@registry.add(
    "WKS-006",
    "Workspace region is compatible with its agents and sources",
    W,
    Dimension.ARCHITECTURE,
    Severity.BLOCKING,
    "Co-locate the workspace, its capacity and its data sources, or obtain cross-geo approval.",
    effort=Effort.L,
    owner_role="Platform Engineer",
)
def region_compatibility(subject: dict) -> RuleOutcome:
    gap = require(subject, "region", "source_regions")
    if gap:
        return gap
    region = subject["region"]
    source_regions = set(subject["source_regions"] or [])
    if not source_regions:
        return RuleOutcome.not_applicable("no cross-region source declared")
    foreign = sorted(source_regions - {region})
    if not foreign:
        return RuleOutcome.passed(
            f"all sources are in {region}",
            evidence=evidence("fabric_rest", "workspace.region"),
        )
    if subject.get("cross_geo_approved"):
        return RuleOutcome.partial(
            0.6,
            f"cross-region sources {foreign} are approved",
            observed={"foreign_regions": foreign},
            evidence=evidence("fabric_rest", "workspace.region"),
        )
    return RuleOutcome.failed(
        f"sources in {foreign} differ from the workspace region {region} without approval",
        observed={"foreign_regions": foreign},
        evidence=evidence("fabric_rest", "workspace.region"),
    )


@registry.add(
    "WKS-007",
    "Workspace is actively used",
    W,
    Dimension.OPERATIONS,
    Severity.MINOR,
    "Archive or decommission dormant workspaces instead of exposing them to agents.",
    effort=Effort.S,
    owner_role="Workspace Admin",
)
def workspace_activity(subject: dict) -> RuleOutcome:
    gap = require(subject, "days_since_last_activity")
    if gap:
        return gap
    days = subject["days_since_last_activity"]
    if days <= DORMANCY_DAYS:
        return RuleOutcome.passed(
            f"last activity {days} day(s) ago",
            observed={"days": days},
            evidence=evidence("activity_events", "workspace.activity"),
        )
    return RuleOutcome.failed(
        f"no activity for {days} days (dormancy threshold {DORMANCY_DAYS})",
        observed={"days": days},
        evidence=evidence("activity_events", "workspace.activity"),
    )


@registry.add(
    "WKS-008",
    "Scheduled refreshes are healthy",
    W,
    Dimension.OPERATIONS,
    Severity.MAJOR,
    "Fix failing refreshes; an agent answering from stale data produces confidently wrong answers.",
    effort=Effort.M,
    owner_role="Data Engineer",
)
def refresh_health(subject: dict) -> RuleOutcome:
    gap = require(subject, "refresh_total", "refresh_failed")
    if gap:
        return gap
    total = subject["refresh_total"]
    if total <= 0:
        return RuleOutcome.not_applicable("no scheduled refresh in this workspace")
    succeeded = total - subject["refresh_failed"]
    return graded(
        ratio(succeeded, total),
        f"{succeeded}/{total} refreshes succeeded over the observation window",
        pass_at=0.95,
        observed={"failed": subject["refresh_failed"]},
        ev=evidence("fabric_rest", "workspace.refreshHistory"),
    )


@registry.add(
    "WKS-009",
    "Workspace inventory was fully retrieved",
    W,
    Dimension.COVERAGE,
    Severity.MAJOR,
    "Re-run the scan for this workspace and investigate any schemaRetrievalError before trusting its score.",
    effort=Effort.S,
    owner_role="Platform Engineer",
)
def workspace_scan_coverage(subject: dict) -> RuleOutcome:
    gap = require(subject, "items_total", "items_scanned")
    if gap:
        return gap
    total = subject["items_total"]
    if total <= 0:
        return RuleOutcome.not_applicable("workspace contains no assessable item")
    errors = subject.get("scan_errors") or []
    covered = ratio(subject["items_scanned"], total)
    if errors:
        covered = min(covered, 0.7)
    return graded(
        covered,
        f"{subject['items_scanned']}/{total} items scanned, {len(errors)} scan error(s)",
        pass_at=1.0,
        observed={"scan_errors": errors},
        ev=evidence("scanner_api", "workspace.items"),
    )


@registry.add(
    "WKS-010",
    "The hosting capacity is running",
    W,
    Dimension.OPERATIONS,
    Severity.BLOCKING,
    "Resume the capacity: a suspended or paused capacity serves no Copilot or Data Agent request, whatever its SKU.",
    effort=Effort.S,
    owner_role="Capacity Administrator",
)
def workspace_capacity_state(subject: dict) -> RuleOutcome:
    if subject.get("capacity_sku") == "":
        return RuleOutcome.not_applicable("workspace has no dedicated capacity")
    gap = require(subject, "capacity_state")
    if gap:
        return gap
    state = subject["capacity_state"]
    if state.lower() == "active":
        return RuleOutcome.passed(
            f"capacity is {state}",
            observed={"state": state},
            evidence=evidence("fabric_rest", "capacities[].state"),
        )
    return RuleOutcome.failed(
        f"capacity is {state}, so it cannot serve agent workloads",
        observed={"state": state},
        evidence=evidence("fabric_rest", "capacities[].state"),
    )
