"""Dated facts about known Microsoft IQ consumption surfaces.

This module is data only. Rules, scoring, collectors, and object-type definitions do
not import or read it. The registry is a precondition input to the Sprint 6.2
per-surface verdict decision; it is not that decision and changes no assessment result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


PrerequisiteKind: TypeAlias = Literal[
    "licence",
    "tenant_setting",
    "capacity",
    "region",
    "publication",
    "billing",
    "permission",
    "limitation",
]
SurfaceStatus: TypeAlias = Literal["GA", "preview"]


@dataclass(frozen=True)
class Prerequisite:
    kind: PrerequisiteKind
    statement: str
    source: str
    read_on: str


@dataclass(frozen=True)
class ConsumptionSurface:
    key: str
    name: str
    status: SurfaceStatus
    grounds_on: tuple[str, ...]
    prerequisites: tuple[Prerequisite, ...]
    review_by: str


REGISTRY_VERSION = "2026.09.27"
REGISTRY_READ_ON = "2026-09-27"

M365_COPILOT_SOURCE = (
    "https://learn.microsoft.com/fabric/iq/connectors/"
    "microsoft-365-copilot-overview"
)
COWORK_SOURCE = "https://learn.microsoft.com/fabric/iq/connectors/cowork-overview"
COPILOT_ADMIN_SOURCE = (
    "https://learn.microsoft.com/fabric/admin/service-admin-portal-copilot"
)
DATA_AGENT_M365_SOURCE = (
    "https://learn.microsoft.com/fabric/data-science/"
    "data-agent-microsoft-365-copilot"
)
DATA_AGENT_CONCEPT_SOURCE = (
    "https://learn.microsoft.com/fabric/data-science/concept-data-agent"
)
DATA_AGENT_TENANT_SETTINGS_SOURCE = (
    "https://learn.microsoft.com/fabric/data-science/data-agent-tenant-settings"
)
DATA_AGENT_FOUNDRY_SOURCE = (
    "https://learn.microsoft.com/fabric/data-science/data-agent-foundry"
)
FABRIC_IQ_SOURCE = "https://learn.microsoft.com/fabric/iq/overview"


CONSUMPTION_SURFACES: tuple[ConsumptionSurface, ...] = (
    ConsumptionSurface(
        key="m365_copilot_chat",
        name="Microsoft 365 Copilot Chat",
        status="GA",
        grounds_on=("semantic_model", "report", "data_agent", "ontology"),
        prerequisites=(
            Prerequisite(
                "licence",
                "Every user requires a Microsoft 365 Copilot Premium licence.",
                M365_COPILOT_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "tenant_setting",
                "Fabric data available in M365 Copilot must be enabled in the "
                "Microsoft 365 admin center; it is on by default.",
                M365_COPILOT_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "tenant_setting",
                "Share Fabric data with your Microsoft 365 services must be enabled.",
                M365_COPILOT_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "tenant_setting",
                "Azure OpenAI cross-geo processing is required for tenants outside "
                "the US and EU.",
                M365_COPILOT_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "capacity",
                "Embedded A and EM capacity SKUs are unsupported.",
                M365_COPILOT_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "region",
                "Regions where Power BI is the only Fabric workload are unsupported.",
                M365_COPILOT_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "limitation",
                "Semantic-model URLs can be pasted; organizational-app report URLs "
                "cannot be pasted, although those reports can be attached.",
                M365_COPILOT_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "publication",
                "Data agents and ontologies are reachable only through an explicitly "
                "published Microsoft 365 agent.",
                M365_COPILOT_SOURCE,
                REGISTRY_READ_ON,
            ),
        ),
        review_by="2026-12-26",
    ),
    ConsumptionSurface(
        key="m365_copilot_cowork",
        name="Microsoft 365 Copilot Cowork",
        status="GA",
        grounds_on=("report", "semantic_model"),
        prerequisites=(
            Prerequisite(
                "publication",
                "Cowork is installed by default.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "licence",
                "Users require Microsoft 365 Copilot licensing.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "tenant_setting",
                "Fabric data available in M365 Copilot must be enabled in the "
                "Microsoft 365 admin center; it is on by default.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "tenant_setting",
                "Share Fabric data with your Microsoft 365 services must be enabled.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "billing",
                "Usage-based consumption billing must be enabled.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "permission",
                "Users need Read permission on both the Power BI report and its "
                "semantic model in the home tenant.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "limitation",
                "DLP is not supported in Cowork.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "limitation",
                "Discovery uses endorsements, and Verified Answers are supported.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "region",
                "Value search is available only where the feature is available in "
                "the user's region.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "limitation",
                "Grounding is limited to Power BI reports and their semantic models, "
                "including reports in workspace apps.",
                COWORK_SOURCE,
                REGISTRY_READ_ON,
            ),
        ),
        review_by="2026-12-19",
    ),
    ConsumptionSurface(
        key="power_bi_agent_m365",
        name="Standalone Copilot in Power BI and Power BI agent in Microsoft 365",
        status="preview",
        grounds_on=("semantic_model", "report"),
        prerequisites=(
            Prerequisite(
                "tenant_setting",
                "Users can access a standalone, cross-item Copilot in Power BI "
                "experience (preview) must be enabled; this also enables the Power BI "
                "agent in Microsoft 365.",
                COPILOT_ADMIN_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "tenant_setting",
                "Only show approved items in the standalone Copilot in Power BI "
                "experience (preview) optionally restricts search to semantic models "
                "marked Approved for Copilot.",
                COPILOT_ADMIN_SOURCE,
                REGISTRY_READ_ON,
            ),
        ),
        review_by="2026-12-12",
    ),
    ConsumptionSurface(
        key="fabric_data_agent_in_fabric",
        name="Fabric data agent in Fabric",
        status="GA",
        grounds_on=(
            "warehouse",
            "lakehouse",
            "semantic_model",
            "kql_database",
            "mirrored_database",
            "ontology",
        ),
        prerequisites=(
            Prerequisite(
                "capacity",
                "A paid F2 or higher Fabric capacity, or a P1 or higher Power BI "
                "Premium per capacity with Microsoft Fabric enabled, is required.",
                DATA_AGENT_CONCEPT_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "tenant_setting",
                "Cross-geo processing for AI and cross-geo storing for AI must be "
                "enabled.",
                DATA_AGENT_TENANT_SETTINGS_SOURCE,
                REGISTRY_READ_ON,
            ),
        ),
        review_by="2026-12-05",
    ),
    ConsumptionSurface(
        key="fabric_data_agent_m365",
        name="Fabric data agent in Microsoft 365",
        status="preview",
        grounds_on=("data_agent",),
        prerequisites=(
            Prerequisite(
                "capacity",
                "A paid F2+ or P1+ capacity SKU with Fabric enabled is required.",
                DATA_AGENT_M365_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "licence",
                "Users require a Microsoft 365 Copilot licence or an Office 365 "
                "commercial licence.",
                DATA_AGENT_M365_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "publication",
                "The data agent must be published with Publish to Agent Store before "
                "it can be mentioned in Teams or Copilot.",
                DATA_AGENT_M365_SOURCE,
                REGISTRY_READ_ON,
            ),
        ),
        review_by="2026-11-28",
    ),
    ConsumptionSurface(
        key="fabric_data_agent_external",
        name="Fabric data agent via Foundry, Copilot Studio, or MCP server",
        status="preview",
        grounds_on=("data_agent",),
        prerequisites=(
            Prerequisite(
                "publication",
                "Fabric data agents can be published across Foundry, Copilot Studio, "
                "and custom applications.",
                FABRIC_IQ_SOURCE,
                REGISTRY_READ_ON,
            ),
            Prerequisite(
                "limitation",
                "Responses may be sent outside of Fabric's compliance boundary or "
                "geographic region.",
                DATA_AGENT_FOUNDRY_SOURCE,
                REGISTRY_READ_ON,
            ),
        ),
        review_by="2026-11-21",
    ),
    ConsumptionSurface(
        key="ontology",
        name="Ontology",
        status="preview",
        grounds_on=("ontology",),
        prerequisites=(
            Prerequisite(
                "limitation",
                "Ontology is listed as a preview Fabric IQ workload item.",
                FABRIC_IQ_SOURCE,
                REGISTRY_READ_ON,
            ),
        ),
        review_by="2026-11-14",
    ),
    ConsumptionSurface(
        key="operations_agent",
        name="Operations agent",
        # The overview labels the IQ workload, not this item, preview: the status
        # is inherited from the workload label.
        status="preview",
        grounds_on=("operations_agent",),
        prerequisites=(
            Prerequisite(
                "limitation",
                "Operations agent is listed as an item of the Fabric IQ (preview) "
                "workload; the page does not label the item itself preview.",
                FABRIC_IQ_SOURCE,
                REGISTRY_READ_ON,
            ),
        ),
        review_by="2026-11-07",
    ),
)


__all__ = [
    "CONSUMPTION_SURFACES",
    "REGISTRY_READ_ON",
    "REGISTRY_VERSION",
    "ConsumptionSurface",
    "Prerequisite",
    "PrerequisiteKind",
    "SurfaceStatus",
]
