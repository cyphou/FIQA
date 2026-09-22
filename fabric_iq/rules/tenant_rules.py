"""Tenant-level readiness rules.

Evidence comes from the Fabric admin tenant settings, the capacity inventory
and the scan telemetry. Nothing here inspects an individual artifact.
"""

from __future__ import annotations

from fabric_iq.models import Dimension, Effort, ObjectType, RuleOutcome, Severity
from fabric_iq.rules.base import evidence, graded, ratio, registry, require

T = ObjectType.TENANT
DOCS_COPILOT = "https://learn.microsoft.com/fabric/admin/service-admin-portal-copilot"
DOCS_CAPACITY = "https://learn.microsoft.com/fabric/enterprise/capacity-planning-overview"
DOCS_SCANNER = "https://learn.microsoft.com/fabric/governance/metadata-scanning-overview"

#: SKUs able to host Copilot and Fabric Data Agent workloads.
ELIGIBLE_FABRIC_SKUS = {"F2", "F4", "F8", "F16", "F32", "F64", "F128", "F256", "F512", "F1024", "F2048"}
ELIGIBLE_PREMIUM_SKUS = {"P1", "P2", "P3", "P4", "P5"}

#: F-capacity-unit equivalence for Premium SKUs, per Microsoft's published mapping.
_PREMIUM_SKU_F_UNITS = {"P1": 64, "P2": 128, "P3": 256, "P4": 512, "P5": 1024}

#: Below this many F-capacity-units, Copilot workloads and Data Agents only run
#: for users assigned to a designated Fabric Copilot capacity.
COPILOT_NATIVE_F_UNITS = 64


def _sku_is_eligible(sku: str) -> bool:
    normalized = (sku or "").strip().upper()
    return normalized in ELIGIBLE_FABRIC_SKUS or normalized in ELIGIBLE_PREMIUM_SKUS


def _sku_f_units(sku: str) -> int:
    """Return the F-capacity-unit equivalent of a SKU, or 0 if unrecognised."""
    normalized = (sku or "").strip().upper()
    if normalized in _PREMIUM_SKU_F_UNITS:
        return _PREMIUM_SKU_F_UNITS[normalized]
    if normalized.startswith("F") and normalized[1:].isdigit():
        return int(normalized[1:])
    return 0


@registry.add(
    "TEN-001",
    "Fabric is enabled for the target audience",
    T,
    Dimension.GOVERNANCE,
    Severity.BLOCKING,
    "Enable Microsoft Fabric in the admin portal for the security groups that will consume Fabric IQ.",
    weight=2.0,
    effort=Effort.S,
    owner_role="Fabric Administrator",
    docs=DOCS_COPILOT,
)
def fabric_enabled(subject: dict) -> RuleOutcome:
    gap = require(subject, "fabric_enabled")
    if gap:
        return gap
    if subject["fabric_enabled"]:
        return RuleOutcome.passed(
            "Fabric is enabled at tenant level",
            evidence=evidence("tenant_settings", "settings.fabric_enabled"),
        )
    return RuleOutcome.failed(
        "Fabric is disabled at tenant level; no Fabric IQ workload can run",
        evidence=evidence("tenant_settings", "settings.fabric_enabled"),
    )


@registry.add(
    "TEN-002",
    "Copilot and AI agent tenant settings are enabled",
    T,
    Dimension.AI_READINESS,
    Severity.BLOCKING,
    "Enable 'Copilot and Azure OpenAI' and the agent settings for the target security groups.",
    weight=2.0,
    effort=Effort.S,
    owner_role="Fabric Administrator",
    docs=DOCS_COPILOT,
)
def copilot_enabled(subject: dict) -> RuleOutcome:
    gap = require(subject, "copilot_enabled", "agents_enabled")
    if gap:
        return gap
    if subject["copilot_enabled"] and subject["agents_enabled"]:
        return RuleOutcome.passed(
            "Copilot and agent settings are enabled",
            evidence=evidence("tenant_settings", "settings.copilot"),
        )
    disabled = [
        name
        for name, flag in (("copilot", subject["copilot_enabled"]), ("agents", subject["agents_enabled"]))
        if not flag
    ]
    return RuleOutcome.failed(
        f"Disabled tenant settings: {', '.join(disabled)}",
        observed={"disabled": disabled},
        evidence=evidence("tenant_settings", "settings.copilot"),
    )


@registry.add(
    "TEN-003",
    "Copilot is scoped to security groups rather than the whole organisation",
    T,
    Dimension.SECURITY,
    Severity.MAJOR,
    "Restrict the Copilot and agent tenant settings to named Entra security groups during the rollout.",
    effort=Effort.S,
    owner_role="Fabric Administrator",
    docs=DOCS_COPILOT,
)
def copilot_scoped(subject: dict) -> RuleOutcome:
    gap = require(subject, "copilot_security_groups")
    if gap:
        return gap
    groups = subject["copilot_security_groups"]
    if groups:
        return RuleOutcome.passed(
            f"Copilot scoped to {len(groups)} security group(s)",
            observed={"groups": len(groups)},
            evidence=evidence("tenant_settings", "settings.copilot.security_groups"),
        )
    return RuleOutcome.failed(
        "Copilot is enabled for the entire organisation with no security group scoping",
        evidence=evidence("tenant_settings", "settings.copilot.security_groups"),
    )


@registry.add(
    "TEN-004",
    "An eligible capacity SKU is available",
    T,
    Dimension.ARCHITECTURE,
    Severity.BLOCKING,
    "Provision or assign a Fabric F2+ or Power BI Premium P1+ capacity for the Fabric IQ workload.",
    weight=2.0,
    effort=Effort.M,
    owner_role="Capacity Administrator",
    docs=DOCS_CAPACITY,
)
def eligible_capacity(subject: dict) -> RuleOutcome:
    gap = require(subject, "capacities")
    if gap:
        return gap
    capacities = subject["capacities"]
    eligible = [c for c in capacities if _sku_is_eligible(c.get("sku", ""))]
    if eligible:
        return RuleOutcome.passed(
            f"{len(eligible)} of {len(capacities)} capacities are Copilot-eligible",
            observed={"eligible_skus": sorted({c.get("sku") for c in eligible})},
            evidence=evidence("fabric_rest", "capacities"),
        )
    return RuleOutcome.failed(
        "No Fabric F2+ or Premium P1+ capacity found",
        observed={"skus": sorted({c.get("sku", "?") for c in capacities})},
        evidence=evidence("fabric_rest", "capacities"),
    )


@registry.add(
    "TEN-005",
    "No capacity is suspended or persistently throttled",
    T,
    Dimension.OPERATIONS,
    Severity.MAJOR,
    "Resume suspended capacities and smooth or optimise the workloads causing sustained throttling before go-live.",
    effort=Effort.L,
    owner_role="Capacity Administrator",
    docs=DOCS_CAPACITY,
)
def capacity_health(subject: dict) -> RuleOutcome:
    gap = require(subject, "capacities")
    if gap:
        return gap
    capacities = subject["capacities"]
    if not capacities:
        return RuleOutcome.not_evaluated("no capacity returned by the inventory")
    unhealthy = [
        c.get("name", c.get("id", "?"))
        for c in capacities
        if (c.get("state") or "").lower() not in ("active", "")
        or bool(c.get("throttled"))
    ]
    healthy = len(capacities) - len(unhealthy)
    return graded(
        ratio(healthy, len(capacities)),
        f"{healthy}/{len(capacities)} capacities healthy",
        observed={"unhealthy": unhealthy},
        ev=evidence("capacity_metrics", "capacities[].state"),
    )


@registry.add(
    "TEN-006",
    "Cross-geo processing is approved when the agent and its sources differ in region",
    T,
    Dimension.SECURITY,
    Severity.BLOCKING,
    "Either co-locate the agent and its data, or obtain and record formal approval for cross-geo processing and storage.",
    effort=Effort.M,
    owner_role="Compliance Officer",
    docs=DOCS_COPILOT,
)
def cross_geo_approved(subject: dict) -> RuleOutcome:
    gap = require(subject, "cross_geo_required", "cross_geo_approved")
    if gap:
        return gap
    if not subject["cross_geo_required"]:
        return RuleOutcome.not_applicable("all workloads are processed in their home region")
    if subject["cross_geo_approved"]:
        return RuleOutcome.passed(
            "Cross-geo processing is required and formally approved",
            evidence=evidence("tenant_settings", "settings.cross_geo"),
        )
    return RuleOutcome.failed(
        "Cross-geo processing is required but has not been approved",
        evidence=evidence("tenant_settings", "settings.cross_geo"),
    )


@registry.add(
    "TEN-007",
    "Metadata scanning is configured with a dedicated service principal",
    T,
    Dimension.COVERAGE,
    Severity.MAJOR,
    "Enable the admin API service principal setting, bind it to a dedicated security group, and schedule the scanner.",
    effort=Effort.M,
    owner_role="Fabric Administrator",
    docs=DOCS_SCANNER,
)
def scanner_configured(subject: dict) -> RuleOutcome:
    gap = require(subject, "scanner_enabled", "scanner_service_principal")
    if gap:
        return gap
    if subject["scanner_enabled"] and subject["scanner_service_principal"]:
        return RuleOutcome.passed(
            "Scanner APIs are enabled for a dedicated service principal",
            evidence=evidence("tenant_settings", "settings.scanner"),
        )
    if subject["scanner_enabled"]:
        return RuleOutcome.partial(
            0.5,
            "Scanner APIs are enabled but run under a delegated admin account",
            evidence=evidence("tenant_settings", "settings.scanner"),
        )
    return RuleOutcome.failed(
        "Metadata scanning is not enabled; the assessment cannot reach tenant-wide coverage",
        evidence=evidence("tenant_settings", "settings.scanner"),
    )


@registry.add(
    "TEN-008",
    "Inventory coverage of active workspaces is sufficient",
    T,
    Dimension.COVERAGE,
    Severity.MAJOR,
    "Investigate scan failures and re-run a full scan so that every active workspace has fresh metadata.",
    weight=1.5,
    effort=Effort.M,
    owner_role="Platform Engineer",
    docs=DOCS_SCANNER,
)
def inventory_coverage(subject: dict) -> RuleOutcome:
    gap = require(subject, "workspaces_total", "workspaces_scanned")
    if gap:
        return gap
    total = subject["workspaces_total"]
    scanned = subject["workspaces_scanned"]
    if total <= 0:
        return RuleOutcome.not_evaluated("no workspace reported by the inventory")
    covered = ratio(scanned, total)
    return graded(
        covered,
        f"{scanned}/{total} workspaces scanned",
        pass_at=0.95,
        observed={"scanned": scanned, "total": total},
        ev=evidence("scanner_api", "workspaces"),
    )


@registry.add(
    "TEN-009",
    "Sensitivity labels are applied to Fabric IQ content",
    T,
    Dimension.SECURITY,
    Severity.MAJOR,
    "Publish and enforce sensitivity labels for the workspaces exposed to agents, and enable mandatory labelling.",
    effort=Effort.L,
    owner_role="Compliance Officer",
    docs="https://learn.microsoft.com/fabric/governance/microsoft-purview-fabric",
)
def sensitivity_labels(subject: dict) -> RuleOutcome:
    gap = require(subject, "sensitivity_labels_enabled", "labelled_item_ratio")
    if gap:
        return gap
    if not subject["sensitivity_labels_enabled"]:
        return RuleOutcome.failed(
            "Sensitivity labels are not enabled at tenant level",
            evidence=evidence("tenant_settings", "settings.information_protection"),
        )
    return graded(
        float(subject["labelled_item_ratio"]),
        f"{subject['labelled_item_ratio']:.0%} of items carry a sensitivity label",
        pass_at=0.9,
        ev=evidence("scanner_api", "items[].sensitivityLabel"),
    )


@registry.add(
    "TEN-010",
    "Tenant ownership and audit are established",
    T,
    Dimension.GOVERNANCE,
    Severity.MAJOR,
    "Name a platform owner, a security owner and a business owner, and confirm audit log retention for agent prompts.",
    effort=Effort.S,
    owner_role="Program Owner",
)
def tenant_ownership(subject: dict) -> RuleOutcome:
    gap = require(subject, "owners", "audit_log_enabled")
    if gap:
        return gap
    owners = subject["owners"] or {}
    required = ("platform", "security", "business")
    present = [role for role in required if owners.get(role)]
    score = ratio(len(present), len(required))
    if not subject["audit_log_enabled"]:
        score = min(score, 0.5)
    return graded(
        score,
        f"owners defined: {', '.join(present) or 'none'}; audit log enabled: {subject['audit_log_enabled']}",
        observed={"missing_owners": [r for r in required if r not in present]},
        ev=evidence("governance_register", "owners"),
    )


@registry.add(
    "TEN-011",
    "Capacities can be designated as Fabric Copilot capacities",
    T,
    Dimension.AI_READINESS,
    Severity.MAJOR,
    "Re-enable the 'Capacities can be designated as Fabric Copilot capacities' tenant setting, scoped to the "
    "capacity administrators who need it, so that capacities smaller than F64 can still be covered for Copilot "
    "and Data Agent workloads.",
    effort=Effort.S,
    owner_role="Fabric Administrator",
    docs=DOCS_COPILOT + "#capacities-can-be-designated-as-copilot-in-fabric-capacities",
)
def copilot_capacity_designation_enabled(subject: dict) -> RuleOutcome:
    gap = require(subject, "copilot_capacity_designation_enabled")
    if gap:
        return gap
    if subject["copilot_capacity_designation_enabled"]:
        return RuleOutcome.passed(
            "Capacity administrators can designate Fabric Copilot capacities",
            evidence=evidence("tenant_settings", "settings.copilot_capacity_designation"),
        )
    return RuleOutcome.failed(
        "The tenant setting is off, so no capacity smaller than F64 can ever be covered for Copilot or Data "
        "Agent workloads, whatever its SKU or workspace configuration",
        evidence=evidence("tenant_settings", "settings.copilot_capacity_designation"),
    )


@registry.add(
    "TEN-012",
    "Microsoft Purview governance policies are reviewed for agent-accessible data",
    T,
    Dimension.GOVERNANCE,
    Severity.MAJOR,
    "Review Purview data loss prevention policies for Fabric Data Warehouse (GA) and access restriction "
    "policies for KQL Database, SQL Database and Data Warehouse (preview) covering every source a Data Agent "
    "can query, and tighten workspace or OneLake permissions directly where those policies do not apply: an "
    "agent runs under the requesting user's effective permissions, so DLP and sensitivity labels alone do not "
    "restrict what it can surface.",
    effort=Effort.M,
    owner_role="Compliance Officer",
    docs="https://learn.microsoft.com/fabric/data-science/concept-data-agent#prerequisites",
)
def purview_governance_reviewed(subject: dict) -> RuleOutcome:
    gap = require(subject, "purview_dlp_reviewed")
    if gap:
        return gap
    if subject["purview_dlp_reviewed"]:
        return RuleOutcome.passed(
            "Purview DLP and access restriction policies were reviewed for agent-accessible data",
            evidence=evidence("governance_register", "purview.dlp_review"),
        )
    return RuleOutcome.failed(
        "No record that Purview DLP or access restriction policies were reviewed for the data sources agents "
        "can query; agents inherit the requesting user's permissions, so this is not covered by policy alone",
        evidence=evidence("governance_register", "purview.dlp_review"),
    )
