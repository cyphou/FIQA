"""Power BI report generator (PBIP project).

Produces a hand-authored Power BI Project (``.pbip``) that a reviewer can open
in Power BI Desktop without any pipeline, gateway or write access to the
assessed tenant: three flat CSV exports feed a small semantic model (TMSL
``model.bim``, the long-stable Analysis Services Tabular format) and a
handful of report pages (legacy ``report.json``, kept deliberately simple:
only ``card`` and ``tableEx`` visuals, no custom visuals, no complex
filters) so the generated JSON stays inside what can be reasoned about and
validated (``json.loads`` + structural checks) without opening Desktop.

Design constraints, matching the rest of the project:

* stdlib only -- no third-party PBI SDK, everything is hand-built JSON/CSV.
* strictly read-only with respect to the assessed tenant: this module only
  *writes local files* derived from an already-computed :class:`AssessmentRun`
  and :class:`RemediationBacklog`.
* never silently drops data: every scorecard, finding and backlog item is
  exported as a CSV row, so nothing in the report is invented.

A companion theme JSON file (public, stable Power BI Theme schema) ships
alongside the project so a reviewer can apply the FUAM/FCA-style teal palette
via *View > Themes > Browse for themes* -- kept as a separate opt-in step
rather than embedded in the report definition, since the legacy embedding
mechanism is not part of any public schema.
"""

from __future__ import annotations

import csv
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from fabric_iq.lakehouse import GOLD_TABLES, gold_mart_rows
from fabric_iq.models import AssessmentRun
from fabric_iq.remediation import RemediationBacklog

#: Brand palette, matching the HTML report (see reporting.py).
BRAND_DARK = "#0b4f43"
BRAND = "#0f6d5c"
BRAND_LIGHT = "#1a8a72"
BRAND_BG = "#f4f6f4"

PROJECT_NAME = "IsFabricReadyForIQ"

#: OneLake's ADLS Gen2 (DFS) endpoint, shared by every Fabric tenant.
ONELAKE_DFS_URL = "https://onelake.dfs.fabric.microsoft.com"


def _new_guid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------
# Column specs: (csv field, Power Query type token, TMSL dataType, format string)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    name: str
    pq_type: str  # Power Query type literal used in Table.TransformColumnTypes
    dax_type: str  # TMSL/AS dataType
    format_string: str | None = None
    summarize_by: str = "none"


#: Base readiness columns shared by the Tenant/Workspace/Object marts --
#: matches :func:`fabric_iq.lakehouse._base_row` field for field.
_BASE_READINESS_COLUMNS: tuple[Column, ...] = (
    Column("run_id", "type text", "string"),
    Column("object_id", "type text", "string"),
    Column("object_name", "type text", "string"),
    Column("object_type", "type text", "string"),
    Column("parent_id", "type text", "string"),
    Column("score", "type number", "double", "0.0"),
    Column("raw_score", "type number", "double", "0.0"),
    Column("status", "type text", "string"),
    Column("eligible", "type logical", "boolean"),
    Column("confidence", "type number", "double", "0%"),
    Column("coverage", "type number", "double", "0%"),
    Column("blocking_findings", "Int64.Type", "int64", "0"),
    Column("failed_findings", "Int64.Type", "int64", "0"),
    Column("ruleset_version", "type text", "string"),
    Column("assessed_at", "type text", "string"),
)

#: ``MartTenantReadiness`` -- one row per tenant scorecard.
TENANT_COLUMNS: tuple[Column, ...] = _BASE_READINESS_COLUMNS + (
    Column("dimension_scores_json", "type text", "string"),
    Column("notes_json", "type text", "string"),
)

#: ``MartWorkspaceReadiness`` -- one row per workspace scorecard.
WORKSPACE_COLUMNS: tuple[Column, ...] = _BASE_READINESS_COLUMNS + (
    Column("dimension_scores_json", "type text", "string"),
)

#: ``MartObjectReadiness`` -- one row per semantic model / report / data agent scorecard.
OBJECT_COLUMNS: tuple[Column, ...] = _BASE_READINESS_COLUMNS + (
    Column("dimension_scores_json", "type text", "string"),
)

#: ``MartBlockingFindings`` -- every blocking (severity=blocking, failed) finding in the run.
BLOCKING_COLUMNS: tuple[Column, ...] = (
    Column("run_id", "type text", "string"),
    Column("rule_id", "type text", "string"),
    Column("title", "type text", "string"),
    Column("object_id", "type text", "string"),
    Column("object_name", "type text", "string"),
    Column("object_type", "type text", "string"),
    Column("dimension", "type text", "string"),
    Column("severity", "type text", "string"),
    Column("remediation", "type text", "string"),
    Column("effort", "type text", "string"),
    Column("owner_role", "type text", "string"),
    Column("docs", "type text", "string"),
    Column("outcome_status", "type text", "string"),
    Column("outcome_score", "type number", "double", "0.0"),
    Column("outcome_detail", "type text", "string"),
    Column("outcome_observed_json", "type text", "string"),
    Column("outcome_evidence_json", "type text", "string"),
)

#: ``MartRemediationBacklog`` -- the prioritized remediation backlog.
BACKLOG_COLUMNS: tuple[Column, ...] = (
    Column("run_id", "type text", "string"),
    Column("rule_id", "type text", "string"),
    Column("title", "type text", "string"),
    Column("object_id", "type text", "string"),
    Column("object_name", "type text", "string"),
    Column("object_type", "type text", "string"),
    Column("severity", "type text", "string"),
    Column("priority", "type number", "double", "0.0"),
    Column("action", "type text", "string"),
    Column("owner_role", "type text", "string"),
    Column("effort", "type text", "string"),
    Column("estimated_days", "type number", "double", "0.0"),
    Column("blocks_go_live", "type logical", "boolean"),
    Column("evidence", "type text", "string"),
    Column("docs", "type text", "string"),
)

#: ``MartCoverageAndFreshness`` -- coverage/confidence per assessed object.
COVERAGE_COLUMNS: tuple[Column, ...] = (
    Column("run_id", "type text", "string"),
    Column("object_id", "type text", "string"),
    Column("object_type", "type text", "string"),
    Column("coverage", "type number", "double", "0%"),
    Column("confidence", "type number", "double", "0%"),
    Column("not_evaluated_count", "Int64.Type", "int64", "0"),
    Column("not_evaluated_rules_json", "type text", "string"),
    Column("is_published", "type logical", "boolean"),
    Column("assessed_at", "type text", "string"),
)

#: Table name -> its Column spec, in Gold-mart order.
MART_COLUMNS: dict[str, tuple[Column, ...]] = {
    "MartTenantReadiness": TENANT_COLUMNS,
    "MartWorkspaceReadiness": WORKSPACE_COLUMNS,
    "MartObjectReadiness": OBJECT_COLUMNS,
    "MartBlockingFindings": BLOCKING_COLUMNS,
    "MartRemediationBacklog": BACKLOG_COLUMNS,
    "MartCoverageAndFreshness": COVERAGE_COLUMNS,
}


# --------------------------------------------------------------------------
# CSV export
# --------------------------------------------------------------------------


def _write_csv(path: str, columns: tuple[Column, ...], rows: Iterable[dict[str, Any]]) -> str:
    fieldnames = [c.name for c in columns]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


# --------------------------------------------------------------------------
# TMSL (model.bim) generation
# --------------------------------------------------------------------------


def _m_type_transform(columns: tuple[Column, ...]) -> str:
    return ", ".join(f'{{"{c.name}", {c.pq_type}}}' for c in columns)


def _m_expression(csv_path: str, columns: tuple[Column, ...]) -> list[str]:
    """Build the Power Query M partition expression for a local CSV table.

    ``csv_path`` is written as an absolute, forward-slash path baked in at
    generation time -- the README documents how to repoint the data source
    if the folder is moved (Transform Data > Data Source Settings).
    """
    abs_path = os.path.abspath(csv_path).replace("\\", "\\\\")
    type_pairs = _m_type_transform(columns)
    lines = [
        "let",
        f'    Source = Csv.Document(File.Contents("{abs_path}"),'
        "[Delimiter=\",\", Columns=" + str(len(columns)) + ", Encoding=65001, "
        "QuoteStyle=QuoteStyle.Csv]),",
        '    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        f'    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{{{type_pairs}}})',
        "in",
        '    #"Changed Type"',
    ]
    return lines


def _tmsl_column(column: Column) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": column.name,
        "dataType": column.dax_type,
        "sourceColumn": column.name,
        "summarizeBy": column.summarize_by,
        "annotations": [{"name": "SummarizationSetBy", "value": "Automatic"}],
    }
    if column.format_string:
        payload["formatString"] = column.format_string
    return payload


def _tmsl_table(
    name: str,
    columns: tuple[Column, ...],
    expression: list[str],
    measures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    table: dict[str, Any] = {
        "name": name,
        "columns": [_tmsl_column(c) for c in columns],
        "partitions": [
            {
                "name": f"{name}-partition",
                "mode": "import",
                "source": {
                    "type": "m",
                    "expression": expression,
                },
            }
        ],
    }
    if measures:
        table["measures"] = measures
    return table


def _tmsl_table_directlake(
    name: str,
    columns: tuple[Column, ...],
    *,
    entity_name: str,
    schema_name: str,
    measures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a TMSL table whose partition is a DirectLake entity partition.

    DirectLake tables have **no** Power Query / M expression per table --
    Analysis Services reads the Delta Parquet files directly. Every column's
    ``sourceColumn`` maps to the Delta column name (identical here since the
    Gold marts are already flattened/scalar), and the single partition
    references the model-level ``DatabaseQuery`` expression (see
    :func:`build_model_bim_directlake`) via ``expressionSource``.
    """
    table: dict[str, Any] = {
        "name": name,
        "columns": [_tmsl_column(c) for c in columns],
        "partitions": [
            {
                "name": f"{name}-partition",
                "mode": "directLake",
                "source": {
                    "type": "entity",
                    "entityName": entity_name,
                    "schemaName": schema_name,
                    "expressionSource": "DatabaseQuery",
                },
            }
        ],
    }
    if measures:
        table["measures"] = measures
    return table


def _measure(name: str, expression: str, format_string: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": name, "expression": expression}
    if format_string:
        payload["formatString"] = format_string
    return payload


#: DAX measures on the MartObjectReadiness table (semantic models, reports,
#: data agents -- the leaf objects). Kept intentionally simple: every one
#: mirrors a figure already surfaced in the HTML/console report so the
#: Power BI numbers can be cross-checked against those artifacts.
OBJECT_MEASURES = [
    _measure("Objects Assessed", "COUNTROWS(MartObjectReadiness)", "0"),
    _measure("Avg Score", "AVERAGE(MartObjectReadiness[score])", "0.0"),
    _measure("Avg Confidence", "AVERAGE(MartObjectReadiness[confidence])", "0%"),
    _measure(
        "Eligible Count",
        "CALCULATE(COUNTROWS(MartObjectReadiness), MartObjectReadiness[eligible] = TRUE)",
        "0",
    ),
    _measure("Eligible %", "DIVIDE([Eligible Count], COUNTROWS(MartObjectReadiness))", "0%"),
    _measure(
        "Not Evaluated Count",
        'CALCULATE(COUNTROWS(MartObjectReadiness), MartObjectReadiness[status] = "not_evaluated")',
        "0",
    ),
]

#: DAX measures on the MartWorkspaceReadiness table.
WORKSPACE_MEASURES = [
    _measure("Workspaces Assessed", "COUNTROWS(MartWorkspaceReadiness)", "0"),
    _measure("Avg Workspace Score", "AVERAGE(MartWorkspaceReadiness[score])", "0.0"),
]

#: DAX measures on the MartTenantReadiness table.
TENANT_MEASURES = [
    _measure("Tenant Score", "AVERAGE(MartTenantReadiness[score])", "0.0"),
    _measure(
        "Tenant Eligible Count",
        "CALCULATE(COUNTROWS(MartTenantReadiness), MartTenantReadiness[eligible] = TRUE)",
        "0",
    ),
]

#: DAX measures on the MartBlockingFindings table -- already pre-filtered to
#: blocking (severity=blocking AND failed) findings, so every row counts.
BLOCKING_MEASURES = [
    _measure("Blocking Findings", "COUNTROWS(MartBlockingFindings)", "0"),
]

BACKLOG_MEASURES = [
    _measure("Backlog Items", "COUNTROWS(MartRemediationBacklog)", "0"),
    _measure("Total Estimated Days", "SUM(MartRemediationBacklog[estimated_days])", "0.0"),
    _measure(
        "Blocking Backlog Items",
        "CALCULATE(COUNTROWS(MartRemediationBacklog), MartRemediationBacklog[blocks_go_live] = TRUE)",
        "0",
    ),
]


def _relationship(from_table: str, from_column: str, to_table: str, to_column: str) -> dict[str, Any]:
    return {
        "name": _new_guid(),
        "fromTable": from_table,
        "fromColumn": from_column,
        "toTable": to_table,
        "toColumn": to_column,
        "fromCardinality": "many",
        "toCardinality": "one",
        "crossFilteringBehavior": "oneDirection",
    }


#: Minimum TMSL compatibility level that recognises the ``directLake``
#: partition mode. Anything lower (e.g. the 1567 default used for the
#: Desktop-only Import model) makes the Fabric Dataset workload reject
#: ``model.bim`` with ``Unrecognized JSON property: mode``.
DIRECTLAKE_COMPATIBILITY_LEVEL = 1604


def _model_bim(
    tables: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    *,
    expressions: list[dict[str, Any]] | None = None,
    compatibility_level: int = 1567,
) -> dict[str, Any]:
    model: dict[str, Any] = {
        "culture": "en-US",
        "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
        "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "sourceQueryCulture": "en-US",
        "tables": tables,
        "relationships": relationships,
        "annotations": [
            {"name": "PBI_QueryOrder", "value": json.dumps([t["name"] for t in tables])},
            {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
        ],
    }
    if expressions:
        model["expressions"] = expressions
    return {
        "name": PROJECT_NAME,
        "compatibilityLevel": compatibility_level,
        "model": model,
    }


def build_model_bim(data_dir: str) -> dict[str, Any]:
    """Build the TMSL ``model.bim`` for a local, Desktop-only PBIP project.

    Partitions read the six Gold-mart CSVs straight off disk via
    ``File.Contents`` -- only valid while the project lives on this machine.
    The model deployed to Fabric uses DirectLake instead (see
    :func:`build_model_bim_directlake`), reading the same six tables
    straight from the Lakehouse's Delta tables with no CSV/M-query step at
    all.
    """
    tables = [
        _tmsl_table(
            "MartTenantReadiness",
            TENANT_COLUMNS,
            _m_expression(os.path.join(data_dir, "MartTenantReadiness.csv"), TENANT_COLUMNS),
            TENANT_MEASURES,
        ),
        _tmsl_table(
            "MartWorkspaceReadiness",
            WORKSPACE_COLUMNS,
            _m_expression(os.path.join(data_dir, "MartWorkspaceReadiness.csv"), WORKSPACE_COLUMNS),
            WORKSPACE_MEASURES,
        ),
        _tmsl_table(
            "MartObjectReadiness",
            OBJECT_COLUMNS,
            _m_expression(os.path.join(data_dir, "MartObjectReadiness.csv"), OBJECT_COLUMNS),
            OBJECT_MEASURES,
        ),
        _tmsl_table(
            "MartBlockingFindings",
            BLOCKING_COLUMNS,
            _m_expression(os.path.join(data_dir, "MartBlockingFindings.csv"), BLOCKING_COLUMNS),
            BLOCKING_MEASURES,
        ),
        _tmsl_table(
            "MartRemediationBacklog",
            BACKLOG_COLUMNS,
            _m_expression(os.path.join(data_dir, "MartRemediationBacklog.csv"), BACKLOG_COLUMNS),
            BACKLOG_MEASURES,
        ),
        _tmsl_table(
            "MartCoverageAndFreshness",
            COVERAGE_COLUMNS,
            _m_expression(os.path.join(data_dir, "MartCoverageAndFreshness.csv"), COVERAGE_COLUMNS),
        ),
    ]
    return _model_bim(tables, [])


def build_model_bim_directlake(
    sql_endpoint_connection_string: str,
    sql_endpoint_id: str,
    schema_name: str = "dbo",
) -> dict[str, Any]:
    """Build the TMSL ``model.bim`` for a DirectLake semantic model.

    Unlike Import mode there is **no per-table Power Query expression** --
    every table's single ``directLake`` partition points at
    ``expressionSource: "DatabaseQuery"``, a single model-level M expression
    (``Sql.Database(connectionString, sqlEndpointId)``) that opens the
    Lakehouse's SQL analytics endpoint. Analysis Services then reads each
    Gold mart's Delta Parquet files directly (no data movement, no refresh,
    no data-source-credentials step to configure manually).

    ``sql_endpoint_connection_string`` and ``sql_endpoint_id`` come from the
    Lakehouse's ``properties.sqlEndpointProperties`` (``connectionString``
    and ``id``), fetched once the endpoint has finished provisioning.
    """
    database_query = [
        "let",
        f'    Source = Sql.Database("{sql_endpoint_connection_string}", "{sql_endpoint_id}")',
        "in",
        "    Source",
    ]
    expressions = [
        {
            "name": "DatabaseQuery",
            "kind": "m",
            "expression": database_query,
            "annotations": [{"name": "PBI_IncludeFutureObjects", "value": "false"}],
        }
    ]
    tables = [
        _tmsl_table_directlake(
            "MartTenantReadiness",
            TENANT_COLUMNS,
            entity_name="MartTenantReadiness",
            schema_name=schema_name,
            measures=TENANT_MEASURES,
        ),
        _tmsl_table_directlake(
            "MartWorkspaceReadiness",
            WORKSPACE_COLUMNS,
            entity_name="MartWorkspaceReadiness",
            schema_name=schema_name,
            measures=WORKSPACE_MEASURES,
        ),
        _tmsl_table_directlake(
            "MartObjectReadiness",
            OBJECT_COLUMNS,
            entity_name="MartObjectReadiness",
            schema_name=schema_name,
            measures=OBJECT_MEASURES,
        ),
        _tmsl_table_directlake(
            "MartBlockingFindings",
            BLOCKING_COLUMNS,
            entity_name="MartBlockingFindings",
            schema_name=schema_name,
            measures=BLOCKING_MEASURES,
        ),
        _tmsl_table_directlake(
            "MartRemediationBacklog",
            BACKLOG_COLUMNS,
            entity_name="MartRemediationBacklog",
            schema_name=schema_name,
            measures=BACKLOG_MEASURES,
        ),
        _tmsl_table_directlake(
            "MartCoverageAndFreshness",
            COVERAGE_COLUMNS,
            entity_name="MartCoverageAndFreshness",
            schema_name=schema_name,
        ),
    ]
    return _model_bim(
        tables,
        [],
        expressions=expressions,
        compatibility_level=DIRECTLAKE_COMPATIBILITY_LEVEL,
    )


# --------------------------------------------------------------------------
# Report (legacy report.json) generation
# --------------------------------------------------------------------------

PAGE_WIDTH = 1280
PAGE_HEIGHT = 720


def _select_column(table: str, alias: str, field_name: str) -> dict[str, Any]:
    return {
        "Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": field_name},
        "Name": f"{table}.{field_name}",
    }


def _select_measure(table: str, alias: str, measure_name: str) -> dict[str, Any]:
    return {
        "Measure": {"Expression": {"SourceRef": {"Source": alias}}, "Property": measure_name},
        "Name": f"{table}.{measure_name}",
    }


def _card_visual(x: int, y: int, width: int, height: int, table: str, measure: str, title: str) -> dict[str, Any]:
    alias = table[0].lower()
    query_ref = f"{table}.{measure}"
    single_visual = {
        "visualType": "card",
        "projections": {"Values": [{"queryRef": query_ref}]},
        "prototypeQuery": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": table, "Type": 0}],
            "Select": [_select_measure(table, alias, measure)],
        },
        "objects": {
            "labels": [{"properties": {"fontSize": {"expr": {"Literal": {"Value": "'28'"}}}}}],
        },
        "vcObjects": {
            "title": [
                {
                    "properties": {
                        "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                        "show": {"expr": {"Literal": {"Value": "true"}}},
                    }
                }
            ],
            "background": [
                {"properties": {"color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{BRAND_BG}'"}}}}}}}
            ],
        },
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": width,
        "height": height,
        "config": json.dumps(
            {
                "name": _new_guid(),
                "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": width, "height": height, "tabOrder": 0}}],
                "singleVisual": single_visual,
            }
        ),
    }


def _table_visual(
    x: int,
    y: int,
    width: int,
    height: int,
    table: str,
    fields: list[str],
    display_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    alias = table[0].lower()
    display_names = display_names or {}
    single_visual = {
        "visualType": "tableEx",
        "projections": {"Values": [{"queryRef": f"{table}.{f}"} for f in fields]},
        "prototypeQuery": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": table, "Type": 0}],
            "Select": [_select_column(table, alias, f) for f in fields],
            "OrderBy": [],
        },
        "columnProperties": {
            f"{table}.{f}": {"displayName": display_names.get(f, f)} for f in fields
        },
        "objects": {
            "grid": [{"properties": {"gridVertical": {"expr": {"Literal": {"Value": "false"}}}}}],
            "columnHeaders": [
                {
                    "properties": {
                        "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{BRAND_DARK}'"}}}}},
                        "bold": {"expr": {"Literal": {"Value": "true"}}},
                    }
                }
            ],
        },
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": width,
        "height": height,
        "config": json.dumps(
            {
                "name": _new_guid(),
                "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": width, "height": height, "tabOrder": 0}}],
                "singleVisual": single_visual,
            }
        ),
    }


def _page(name: str, display_name: str, ordinal: int, visuals: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": name,
        "displayName": display_name,
        "filters": "[]",
        "ordinal": ordinal,
        "visualContainers": visuals,
        "config": json.dumps({"objects": {"section": [{"properties": {"verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}}}}]}}),
        "displayOption": 1,
        "width": PAGE_WIDTH,
        "height": PAGE_HEIGHT,
    }


def _overview_page() -> dict[str, Any]:
    cards = [
        ("MartObjectReadiness", "Objects Assessed", "Objects Assessed"),
        ("MartObjectReadiness", "Avg Score", "Average Score"),
        ("MartObjectReadiness", "Eligible %", "Eligible %"),
        ("MartObjectReadiness", "Avg Confidence", "Avg Confidence"),
        ("MartBlockingFindings", "Blocking Findings", "Blocking Findings"),
        ("MartRemediationBacklog", "Backlog Items", "Backlog Items"),
    ]
    visuals = []
    card_width, card_height, gap, margin = 195, 140, 15, 20
    for i, (table, measure, title) in enumerate(cards):
        x = margin + i * (card_width + gap)
        visuals.append(_card_visual(x, margin, card_width, card_height, table, measure, title))
    return _page("ReportSection", "Overview", 0, visuals)


def _tenant_workspace_page() -> dict[str, Any]:
    tenant_fields = ["object_name", "score", "status", "eligible", "confidence", "coverage", "ruleset_version"]
    tenant_names = {
        "object_name": "Tenant",
        "score": "Score",
        "status": "Status",
        "eligible": "Eligible",
        "confidence": "Confidence",
        "coverage": "Coverage",
        "ruleset_version": "Ruleset",
    }
    workspace_fields = ["object_name", "score", "status", "eligible", "confidence", "coverage"]
    workspace_names = {
        "object_name": "Workspace",
        "score": "Score",
        "status": "Status",
        "eligible": "Eligible",
        "confidence": "Confidence",
        "coverage": "Coverage",
    }
    half_height = (PAGE_HEIGHT - 60) // 2
    tenant_visual = _table_visual(20, 20, PAGE_WIDTH - 40, half_height, "MartTenantReadiness", tenant_fields, tenant_names)
    workspace_visual = _table_visual(
        20, 40 + half_height, PAGE_WIDTH - 40, half_height, "MartWorkspaceReadiness", workspace_fields, workspace_names
    )
    return _page("ReportSection1", "Tenant & Workspaces", 1, [tenant_visual, workspace_visual])


def _object_page() -> dict[str, Any]:
    fields = ["object_name", "object_type", "parent_id", "score", "status", "eligible", "confidence", "coverage"]
    names = {
        "object_name": "Object",
        "object_type": "Type",
        "parent_id": "Workspace",
        "score": "Score",
        "status": "Status",
        "eligible": "Eligible",
        "confidence": "Confidence",
        "coverage": "Coverage",
    }
    visual = _table_visual(20, 20, PAGE_WIDTH - 40, PAGE_HEIGHT - 40, "MartObjectReadiness", fields, names)
    return _page("ReportSection2", "Object Readiness", 2, [visual])


def _blocking_page() -> dict[str, Any]:
    fields = ["object_name", "object_type", "dimension", "severity", "title", "remediation", "owner_role", "effort"]
    names = {
        "object_name": "Object",
        "object_type": "Type",
        "dimension": "Dimension",
        "severity": "Severity",
        "title": "Finding",
        "remediation": "Remediation",
        "owner_role": "Owner",
        "effort": "Effort",
    }
    visual = _table_visual(20, 20, PAGE_WIDTH - 40, PAGE_HEIGHT - 40, "MartBlockingFindings", fields, names)
    return _page("ReportSection3", "Blocking Findings", 3, [visual])


def _backlog_page() -> dict[str, Any]:
    fields = ["priority", "severity", "object_name", "title", "action", "owner_role", "effort", "estimated_days"]
    names = {
        "priority": "Priority",
        "severity": "Severity",
        "object_name": "Object",
        "title": "Finding",
        "action": "Action",
        "owner_role": "Owner",
        "effort": "Effort",
        "estimated_days": "Est. Days",
    }
    visual = _table_visual(20, 20, PAGE_WIDTH - 40, PAGE_HEIGHT - 40, "MartRemediationBacklog", fields, names)
    return _page("ReportSection4", "Remediation Backlog", 4, [visual])


def _coverage_page() -> dict[str, Any]:
    fields = ["object_id", "object_type", "coverage", "confidence", "not_evaluated_count", "is_published", "assessed_at"]
    names = {
        "object_id": "Object",
        "object_type": "Type",
        "coverage": "Coverage",
        "confidence": "Confidence",
        "not_evaluated_count": "Not Evaluated",
        "is_published": "Published",
        "assessed_at": "Assessed At",
    }
    visual = _table_visual(20, 20, PAGE_WIDTH - 40, PAGE_HEIGHT - 40, "MartCoverageAndFreshness", fields, names)
    return _page("ReportSection5", "Coverage & Freshness", 5, [visual])


def build_report_json() -> dict[str, Any]:
    """Build the legacy ``report.json`` document with six fixed pages."""
    sections = [
        _overview_page(),
        _tenant_workspace_page(),
        _object_page(),
        _blocking_page(),
        _backlog_page(),
        _coverage_page(),
    ]
    config = {
        "version": "5.45",
        "themeCollection": {"baseTheme": {"name": "CY23SU08", "version": "5.45", "type": 2}},
        "activeSectionIndex": 0,
        "linguisticSchemaSyncVersion": 0,
        "settings": {
            "useStylableVisualContainerHeader": True,
            "defaultDrillFilterOtherVisuals": True,
            "allowChangeFilterTypes": True,
            "useEnhancedTooltips": True,
            "useDefaultAggregateDisplayName": True,
        },
    }
    return {
        "id": 0,
        "resourcePackages": [],
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "sections": sections,
        "publicCustomVisuals": [],
    }


# --------------------------------------------------------------------------
# Theme (standalone, applied manually via View > Themes > Browse)
# --------------------------------------------------------------------------


def build_theme() -> dict[str, Any]:
    """Build the FUAM/FCA-inspired standalone Power BI theme JSON."""
    return {
        "name": "IsFabricReadyForIQ Teal",
        "dataColors": [
            BRAND, BRAND_LIGHT, BRAND_DARK,
            "#7a6a00", "#a95c00", "#a4262c",
            "#0c5aa6", "#5f6b73",
        ],
        "background": "#ffffff",
        "foreground": "#1b1f1e",
        "tableAccent": BRAND,
        "good": "#107c10",
        "neutral": "#d18b00",
        "bad": "#a4262c",
        "visualStyles": {
            "*": {
                "*": {
                    "*": [
                        {
                            "background": {"solid": {"color": {"solid": {"color": "#ffffff"}}}},
                            "border": {"show": True, "color": {"solid": {"color": "#e3e5e1"}}},
                        }
                    ]
                }
            },
            "card": {
                "*": {
                    "labels": [{"color": {"solid": {"color": BRAND_DARK}}, "fontSize": 28}],
                    "categoryLabels": [{"color": {"solid": {"color": "#667066"}}}],
                }
            },
            "tableEx": {
                "*": {
                    "columnHeaders": [{"fontColor": {"solid": {"color": BRAND_DARK}}, "backColor": {"solid": {"color": "#eef6f4"}}}],
                }
            },
        },
    }


def build_definition_pbir(project_name: str = PROJECT_NAME) -> dict[str, Any]:
    """Build ``definition.pbir`` for the local PBIP project (Desktop use).

    Uses ``datasetReference.byPath`` -- the format Power BI Desktop and Git
    integration use for a report/semantic-model pair that live side by side
    as ``.Report``/``.SemanticModel`` folders on disk. **Not** valid for a
    report created directly through the Fabric REST API: Microsoft's own
    docs state that API-driven deployments must use ``byConnection`` instead
    (see :func:`build_definition_pbir_live`), since there is no folder tree
    for a relative path to resolve against.
    """
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "report/definitionProperties/2.0.0/schema.json"
        ),
        "version": "4.0",
        "datasetReference": {
            "byPath": {"path": f"../{project_name}.SemanticModel"},
        },
    }


def build_definition_pbir_live(semantic_model_id: str) -> dict[str, Any]:
    """Build ``definition.pbir`` for a report deployed through the Fabric REST API.

    Uses ``datasetReference.byConnection`` with a ``semanticmodelid=`` connection
    string -- the format Microsoft's Fabric REST API documentation requires when
    a report is created/updated via the API, as opposed to the ``byPath`` form
    used by :func:`build_definition_pbir` for local PBIP projects.
    """
    if not semantic_model_id:
        raise ValueError("semantic_model_id is required")
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "report/definitionProperties/2.0.0/schema.json"
        ),
        "version": "4.0",
        "datasetReference": {
            "byConnection": {"connectionString": f"semanticmodelid={semantic_model_id}"},
        },
    }


def build_definition_pbism() -> dict[str, Any]:
    """Build ``definition.pbism``: declares the model is stored as TMSL (model.bim)."""
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "semanticModel/definitionProperties/1.0.0/schema.json"
        ),
        "version": "1.0",
    }


def build_report_config() -> dict[str, Any]:
    """Build ``report.config.json``: required alongside ``report.json``."""
    return {"version": "1.0"}


# --------------------------------------------------------------------------
# PBIP project assembly
# --------------------------------------------------------------------------


class PowerBiReportWriter:
    """Writes a self-contained PBIP project for one assessment run."""

    def __init__(self, root: str, project_name: str = PROJECT_NAME) -> None:
        self.root = root
        self.project_name = project_name

    def write_run(self, run: AssessmentRun, backlog: RemediationBacklog) -> str:
        os.makedirs(self.root, exist_ok=True)
        data_dir = os.path.join(self.root, "data")
        os.makedirs(data_dir, exist_ok=True)

        mart_rows = gold_mart_rows(run, backlog, run_id=run.run_id)
        for table_name, columns in MART_COLUMNS.items():
            _write_csv(os.path.join(data_dir, f"{table_name}.csv"), columns, mart_rows[table_name])

        report_dir = os.path.join(self.root, f"{self.project_name}.Report")
        model_dir = os.path.join(self.root, f"{self.project_name}.SemanticModel")
        os.makedirs(report_dir, exist_ok=True)
        os.makedirs(model_dir, exist_ok=True)

        with open(os.path.join(report_dir, "report.json"), "w", encoding="utf-8") as handle:
            json.dump(build_report_json(), handle, indent=2)

        with open(os.path.join(report_dir, "report.config.json"), "w", encoding="utf-8") as handle:
            json.dump(build_report_config(), handle, indent=2)

        # Required in every PBIP report folder (PBIR and PBIR-Legacy alike):
        # without it, Power BI Desktop reports "Required artifact is missing"
        # and refuses to load the project, falling back to a blank report.
        with open(os.path.join(report_dir, "definition.pbir"), "w", encoding="utf-8") as handle:
            json.dump(build_definition_pbir(self.project_name), handle, indent=2)

        with open(os.path.join(model_dir, "model.bim"), "w", encoding="utf-8") as handle:
            json.dump(build_model_bim(data_dir), handle, indent=2)

        # Required in every PBIP semantic model folder: without it, Power BI
        # Desktop reports "Required artifact is missing" for the dataset.
        # Version "1.0" declares the model is stored as TMSL (model.bim),
        # which matches what this generator writes (no TMDL definition/ folder).
        with open(os.path.join(model_dir, "definition.pbism"), "w", encoding="utf-8") as handle:
            json.dump(build_definition_pbism(), handle, indent=2)

        pbip_path = os.path.join(self.root, f"{self.project_name}.pbip")
        pbip_doc = {
            "version": "1.0",
            "artifacts": [{"report": {"path": f"{self.project_name}.Report"}}],
            "settings": {"enableAutoRecovery": True},
        }
        with open(pbip_path, "w", encoding="utf-8") as handle:
            json.dump(pbip_doc, handle, indent=2)

        with open(os.path.join(self.root, "FabricIQ_Theme.json"), "w", encoding="utf-8") as handle:
            json.dump(build_theme(), handle, indent=2)

        self._write_readme(run)
        return self.root

    def _write_readme(self, run: AssessmentRun) -> None:
        readme = f"""# {self.project_name} -- Power BI report

Generated from assessment run `{run.run_id}` (ruleset `{run.ruleset_version}`).

## Open it

1. Open `{self.project_name}.pbip` in Power BI Desktop (November 2023 or
   later, with the *Power BI Project (.pbip) save option* preview/GA feature
   enabled).
2. Desktop will load the `.Report` and `.SemanticModel` folders and prompt to
   refresh -- accept it. The six CSV files under `data/` (one per Gold mart)
   are the only data source; nothing else is contacted.
3. Optional: apply the bundled `FabricIQ_Theme.json` teal theme via
   *View > Themes > Browse for themes*.

## If the CSV files move

The Power Query source uses an absolute path baked in at generation time.
If you move this folder, open *Transform data > Data source settings* in
Power BI Desktop and repoint the six CSV sources at the new `data/` path,
then refresh.

## Pages

* **Overview** -- KPI cards (objects assessed, average score, eligible %,
  average confidence, blocking findings, backlog items).
* **Tenant & Workspaces** -- tenant-level and workspace-level readiness.
* **Object Readiness** -- one row per assessed object with score, status,
  eligibility and confidence.
* **Blocking Findings** -- every blocking (go-live blocking) finding
  recorded during the run.
* **Remediation Backlog** -- the prioritized remediation backlog.
* **Coverage & Freshness** -- coverage, confidence and last-assessed
  timestamps per object.

This project is generated read-only output: it does not write to, or
connect to, the assessed Power BI/Fabric tenant.
"""
        with open(os.path.join(self.root, "README.md"), "w", encoding="utf-8") as handle:
            handle.write(readme)
