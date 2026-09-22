"""Semantic model readiness rules.

These encode the Microsoft guidance for conversational BI: star schema,
explicit measures, business-friendly naming, descriptions, synonyms, the AI
data schema, AI instructions and verified answers.

References:
    https://learn.microsoft.com/power-bi/create-reports/copilot-prepare-data-ai
    https://learn.microsoft.com/fabric/data-science/semantic-model-best-practices
"""

from __future__ import annotations

import re

from fabric_iq.models import Dimension, Effort, ObjectType, RuleOutcome, Severity
from fabric_iq.rules.base import evidence, graded, ratio, registry, require

M = ObjectType.SEMANTIC_MODEL
DOCS_PREP_AI = "https://learn.microsoft.com/power-bi/create-reports/copilot-prepare-data-ai"
DOCS_AGENT_MODEL = "https://learn.microsoft.com/fabric/data-science/semantic-model-best-practices"

#: Only the first 200 characters of a description are read by Copilot.
DESCRIPTION_BUDGET = 200

#: A description shorter than this carries no disambiguating information.
DESCRIPTION_MIN = 15

#: AI instructions are capped by the product.
AI_INSTRUCTIONS_MAX = 10_000

#: Technical naming styles that Copilot cannot interpret literally.
_TECHNICAL_NAME = re.compile(
    r"""(
        ^[A-Z0-9_]{2,}$          # UPPER_SNAKE or ALLCAPS abbreviations
        | _                      # snake_case
        | ^[a-z]+[A-Z]           # camelCase
        | ^(dim|fact|tbl|vw|col|fk|pk)[_A-Z]  # technical prefixes
    )""",
    re.VERBOSE,
)


def _visible(objects: list[dict]) -> list[dict]:
    return [o for o in objects or [] if not o.get("hidden")]


def _usable_description(obj: dict) -> bool:
    text = (obj.get("description") or "").strip()
    return len(text) >= DESCRIPTION_MIN


def _is_technical_name(name: str) -> bool:
    return bool(_TECHNICAL_NAME.search((name or "").strip()))


def _normalize_dax(expression: str) -> str:
    """Normalize a DAX expression so that layout differences do not hide a duplicate.

    Whitespace outside string literals carries no meaning in DAX, so it is
    removed entirely. Text inside double-quoted literals is preserved, because
    ``"North America"`` and ``"NorthAmerica"`` are different values.
    """
    normalized: list[str] = []
    in_literal = False
    index = 0
    text = (expression or "").strip().lower()
    while index < len(text):
        char = text[index]
        if char == '"':
            # A doubled quote is an escaped quote inside a literal, not a delimiter.
            if in_literal and text[index + 1 : index + 2] == '"':
                normalized.append('""')
                index += 2
                continue
            in_literal = not in_literal
            normalized.append(char)
        elif in_literal or not char.isspace():
            normalized.append(char)
        index += 1
    return "".join(normalized)


@registry.add(
    "SEM-001",
    "Model follows a star schema",
    M,
    Dimension.ARCHITECTURE,
    Severity.MAJOR,
    "Split flat or snowflaked tables into conformed dimensions and fact tables before exposing the model to agents.",
    weight=2.0,
    effort=Effort.XL,
    owner_role="Data Modeler",
    docs=DOCS_AGENT_MODEL,
)
def star_schema(subject: dict) -> RuleOutcome:
    gap = require(subject, "tables", "relationships")
    if gap:
        return gap
    tables = subject["tables"]
    if len(tables) <= 1:
        return RuleOutcome.failed(
            "single flat table; Copilot cannot separate metrics from their context",
            evidence=evidence("scanner_api", "model.tables"),
        )
    facts = [t for t in tables if t.get("role") == "fact"]
    dims = [t for t in tables if t.get("role") == "dimension"]
    unclassified = [t.get("name") for t in tables if t.get("role") not in ("fact", "dimension")]
    if not facts or not dims:
        return RuleOutcome.failed(
            f"{len(facts)} fact and {len(dims)} dimension tables identified",
            observed={"unclassified": unclassified},
            evidence=evidence("scanner_api", "model.tables"),
        )
    return graded(
        ratio(len(tables) - len(unclassified), len(tables)),
        f"{len(facts)} facts, {len(dims)} dimensions, {len(unclassified)} unclassified",
        observed={"unclassified": unclassified},
        ev=evidence("scanner_api", "model.tables"),
    )


@registry.add(
    "SEM-002",
    "Relationships are active, valid and unambiguous",
    M,
    Dimension.ARCHITECTURE,
    Severity.BLOCKING,
    "Remove inactive or ambiguous relationship paths and fix mismatched key data types.",
    weight=1.5,
    effort=Effort.L,
    owner_role="Data Modeler",
)
def relationship_integrity(subject: dict) -> RuleOutcome:
    gap = require(subject, "relationships")
    if gap:
        return gap
    relationships = subject["relationships"]
    if not relationships:
        return RuleOutcome.not_applicable("model has no relationship to validate")
    invalid = [r for r in relationships if r.get("invalid")]
    ambiguous = [r for r in relationships if r.get("ambiguous")]
    if invalid or ambiguous:
        return RuleOutcome.failed(
            f"{len(invalid)} invalid and {len(ambiguous)} ambiguous relationship(s)",
            observed={
                "invalid": [r.get("name") for r in invalid],
                "ambiguous": [r.get("name") for r in ambiguous],
            },
            evidence=evidence("scanner_api", "model.relationships"),
        )
    return RuleOutcome.passed(
        f"{len(relationships)} relationships are valid and unambiguous",
        evidence=evidence("scanner_api", "model.relationships"),
    )


@registry.add(
    "SEM-003",
    "Key metrics exist as explicit measures",
    M,
    Dimension.ARCHITECTURE,
    Severity.BLOCKING,
    "Create explicit DAX measures for every business metric; implicit aggregations are not reliably reachable by Copilot.",
    weight=2.0,
    effort=Effort.L,
    owner_role="Data Modeler",
    docs=DOCS_AGENT_MODEL,
)
def explicit_measures(subject: dict) -> RuleOutcome:
    gap = require(subject, "measures")
    if gap:
        return gap
    measures = subject["measures"]
    if not measures:
        return RuleOutcome.failed(
            "model exposes no explicit measure",
            evidence=evidence("scanner_api", "model.measures"),
        )
    return RuleOutcome.passed(
        f"{len(measures)} explicit measures defined",
        observed={"measures": len(measures)},
        evidence=evidence("scanner_api", "model.measures"),
    )


@registry.add(
    "SEM-004",
    "A date dimension is present and marked",
    M,
    Dimension.ARCHITECTURE,
    Severity.MAJOR,
    "Add a dedicated date table, mark it as a date table, and document which date role is the default.",
    effort=Effort.M,
    owner_role="Data Modeler",
)
def date_dimension(subject: dict) -> RuleOutcome:
    gap = require(subject, "tables", "has_time_intelligence")
    if gap:
        return gap
    if not subject["has_time_intelligence"]:
        return RuleOutcome.not_applicable("model carries no time-based analysis")
    date_tables = [t for t in subject["tables"] if t.get("is_date_table")]
    if not date_tables:
        return RuleOutcome.failed(
            "time intelligence is used but no table is marked as a date table",
            evidence=evidence("scanner_api", "model.tables[].isDateTable"),
        )
    return RuleOutcome.passed(
        f"{len(date_tables)} marked date table(s)",
        evidence=evidence("scanner_api", "model.tables[].isDateTable"),
    )


@registry.add(
    "SEM-005",
    "Visible objects use business-friendly names",
    M,
    Dimension.BUSINESS_SEMANTICS,
    Severity.MAJOR,
    "Rename technical identifiers (TR_AMT, dim_customer, camelCase) to the terms business users speak.",
    weight=2.0,
    effort=Effort.L,
    owner_role="Data Modeler",
    docs=DOCS_PREP_AI,
)
def business_friendly_names(subject: dict) -> RuleOutcome:
    gap = require(subject, "tables", "columns", "measures")
    if gap:
        return gap
    objects = _visible(subject["tables"]) + _visible(subject["columns"]) + _visible(subject["measures"])
    if not objects:
        return RuleOutcome.not_evaluated("no visible object returned by the scan")
    technical = [o.get("name") for o in objects if _is_technical_name(o.get("name", ""))]
    return graded(
        ratio(len(objects) - len(technical), len(objects)),
        f"{len(technical)}/{len(objects)} visible objects carry a technical name",
        pass_at=0.98,
        observed={"technical_names": technical[:25]},
        ev=evidence("scanner_api", "model.*.name"),
    )


@registry.add(
    "SEM-006",
    "Visible objects carry a usable description",
    M,
    Dimension.AI_READINESS,
    Severity.MAJOR,
    "Describe every visible table, column and measure: preferred usage, disambiguation, grain and unit.",
    weight=2.0,
    effort=Effort.XL,
    owner_role="Data Steward",
    docs=DOCS_PREP_AI,
)
def description_coverage(subject: dict) -> RuleOutcome:
    gap = require(subject, "tables", "columns", "measures")
    if gap:
        return gap
    objects = _visible(subject["tables"]) + _visible(subject["columns"]) + _visible(subject["measures"])
    if not objects:
        return RuleOutcome.not_evaluated("no visible object returned by the scan")
    described = [o for o in objects if _usable_description(o)]
    undescribed = [o.get("name") for o in objects if not _usable_description(o)]
    return graded(
        ratio(len(described), len(objects)),
        f"{len(described)}/{len(objects)} visible objects described",
        pass_at=0.9,
        observed={"undescribed": undescribed[:25]},
        ev=evidence("scanner_api", "model.*.description"),
    )


@registry.add(
    "SEM-007",
    "Descriptions front-load meaning within the Copilot budget",
    M,
    Dimension.AI_READINESS,
    Severity.MINOR,
    "Rewrite long descriptions so the disambiguating information sits in the first 200 characters.",
    effort=Effort.M,
    owner_role="Data Steward",
    docs=DOCS_PREP_AI,
)
def description_budget(subject: dict) -> RuleOutcome:
    gap = require(subject, "measures", "columns")
    if gap:
        return gap
    described = [
        o
        for o in _visible(subject["measures"]) + _visible(subject["columns"])
        if (o.get("description") or "").strip()
    ]
    if not described:
        return RuleOutcome.not_applicable("no description to evaluate")
    over_budget = [o.get("name") for o in described if len(o["description"]) > DESCRIPTION_BUDGET]
    return graded(
        ratio(len(described) - len(over_budget), len(described)),
        f"{len(over_budget)}/{len(described)} descriptions exceed {DESCRIPTION_BUDGET} characters",
        pass_at=0.95,
        observed={"over_budget": over_budget[:25]},
        ev=evidence("scanner_api", "model.*.description"),
    )


@registry.add(
    "SEM-008",
    "An AI data schema scopes what Copilot sees",
    M,
    Dimension.AI_READINESS,
    Severity.BLOCKING,
    "Configure the AI data schema in Prep data for AI and expose only objects a business user would ask about.",
    weight=2.0,
    effort=Effort.M,
    owner_role="Model Owner",
    docs=DOCS_PREP_AI,
)
def ai_data_schema(subject: dict) -> RuleOutcome:
    gap = require(subject, "ai_data_schema")
    if gap:
        return gap
    schema = subject["ai_data_schema"] or {}
    selected = schema.get("selected_objects")
    if not selected:
        return RuleOutcome.failed(
            "no AI data schema configured; the whole model is exposed to Copilot",
            evidence=evidence("pbip_definition", "Copilot/aiDataSchema"),
        )
    total = subject.get("visible_object_count") or 0
    if total <= 0:
        return RuleOutcome.passed(
            f"{selected} objects selected for AI",
            evidence=evidence("pbip_definition", "Copilot/aiDataSchema"),
        )
    exposure = selected / total
    # Exposing nearly everything defeats the purpose of scoping.
    if exposure > 0.8:
        return RuleOutcome.partial(
            0.4,
            f"AI schema exposes {exposure:.0%} of visible objects; scoping is too broad",
            observed={"selected": selected, "visible": total},
            evidence=evidence("pbip_definition", "Copilot/aiDataSchema"),
        )
    return RuleOutcome.passed(
        f"AI schema exposes {selected}/{total} visible objects",
        observed={"selected": selected, "visible": total},
        evidence=evidence("pbip_definition", "Copilot/aiDataSchema"),
    )


@registry.add(
    "SEM-009",
    "AI schema dependencies are complete",
    M,
    Dimension.AI_READINESS,
    Severity.BLOCKING,
    "Add every column and measure referenced by a selected measure to the AI data schema.",
    weight=1.5,
    effort=Effort.M,
    owner_role="Model Owner",
    docs=DOCS_PREP_AI,
)
def ai_schema_dependencies(subject: dict) -> RuleOutcome:
    gap = require(subject, "ai_data_schema")
    if gap:
        return gap
    schema = subject["ai_data_schema"] or {}
    if not schema.get("selected_objects"):
        return RuleOutcome.not_applicable("no AI data schema configured (see SEM-008)")
    missing_deps = schema.get("missing_dependencies") or []
    if missing_deps:
        return RuleOutcome.failed(
            f"{len(missing_deps)} dependency object(s) referenced but not exposed",
            observed={"missing_dependencies": missing_deps[:25]},
            evidence=evidence("pbip_definition", "Copilot/aiDataSchema"),
        )
    return RuleOutcome.passed(
        "every dependency of a selected measure is exposed",
        evidence=evidence("pbip_definition", "Copilot/aiDataSchema"),
    )


@registry.add(
    "SEM-010",
    "Synonyms cover the vocabulary users actually speak",
    M,
    Dimension.AI_READINESS,
    Severity.MAJOR,
    "Add synonyms for the alternative terms each department uses for the same metric or entity.",
    effort=Effort.L,
    owner_role="Data Steward",
    docs=DOCS_PREP_AI,
)
def synonym_coverage(subject: dict) -> RuleOutcome:
    gap = require(subject, "measures")
    if gap:
        return gap
    measures = _visible(subject["measures"])
    if not measures:
        return RuleOutcome.not_evaluated("no visible measure returned by the scan")
    with_synonyms = [m for m in measures if m.get("synonyms")]
    return graded(
        ratio(len(with_synonyms), len(measures)),
        f"{len(with_synonyms)}/{len(measures)} visible measures have synonyms",
        pass_at=0.6,
        observed={"without_synonyms": [m.get("name") for m in measures if not m.get("synonyms")][:25]},
        ev=evidence("pbip_definition", "Copilot/synonyms"),
    )


@registry.add(
    "SEM-011",
    "AI instructions are present, bounded and non-contradictory",
    M,
    Dimension.AI_READINESS,
    Severity.MAJOR,
    "Write AI instructions covering metric routing, fiscal calendar, date disambiguation and polarity; keep them under 10,000 characters.",
    weight=1.5,
    effort=Effort.M,
    owner_role="Model Owner",
    docs=DOCS_PREP_AI,
)
def ai_instructions(subject: dict) -> RuleOutcome:
    gap = require(subject, "ai_instructions")
    if gap:
        return gap
    text = (subject["ai_instructions"] or "").strip()
    if not text:
        return RuleOutcome.failed(
            "no AI instructions defined",
            evidence=evidence("pbip_definition", "Copilot/aiInstructions"),
        )
    if len(text) > AI_INSTRUCTIONS_MAX:
        return RuleOutcome.failed(
            f"AI instructions are {len(text)} characters, over the {AI_INSTRUCTIONS_MAX} limit",
            observed={"length": len(text)},
            evidence=evidence("pbip_definition", "Copilot/aiInstructions"),
        )
    if len(text) < 200:
        return RuleOutcome.partial(
            0.5,
            f"AI instructions are only {len(text)} characters; routing rules are probably missing",
            observed={"length": len(text)},
            evidence=evidence("pbip_definition", "Copilot/aiInstructions"),
        )
    return RuleOutcome.passed(
        f"AI instructions defined ({len(text)} characters)",
        observed={"length": len(text)},
        evidence=evidence("pbip_definition", "Copilot/aiInstructions"),
    )


@registry.add(
    "SEM-012",
    "Verified answers cover the ambiguous high-value questions",
    M,
    Dimension.AI_READINESS,
    Severity.MINOR,
    "Author verified answers in Power BI Desktop for the most contentious or most asked questions.",
    effort=Effort.L,
    owner_role="Model Owner",
    docs="https://learn.microsoft.com/power-bi/create-reports/copilot-prepare-data-ai-verified-answers",
)
def verified_answers(subject: dict) -> RuleOutcome:
    gap = require(subject, "verified_answers")
    if gap:
        return gap
    count = len(subject["verified_answers"] or [])
    broken = [v.get("question") for v in (subject["verified_answers"] or []) if v.get("broken")]
    if broken:
        return RuleOutcome.failed(
            f"{len(broken)} verified answer(s) reference removed or renamed fields",
            observed={"broken": broken[:10]},
            evidence=evidence("pbip_definition", "Copilot/verifiedAnswers"),
        )
    if count == 0:
        return RuleOutcome.failed(
            "no verified answer configured",
            evidence=evidence("pbip_definition", "Copilot/verifiedAnswers"),
        )
    return graded(
        ratio(count, 5),
        f"{count} verified answer(s) configured",
        pass_at=1.0,
        observed={"count": count},
        ev=evidence("pbip_definition", "Copilot/verifiedAnswers"),
    )


@registry.add(
    "SEM-013",
    "Numeric non-additive columns are not summarised by default",
    M,
    Dimension.BUSINESS_SEMANTICS,
    Severity.MAJOR,
    "Set summarizeBy to None on identifiers, years, month numbers and postal codes.",
    effort=Effort.S,
    owner_role="Data Modeler",
    docs=DOCS_PREP_AI,
)
def summarize_by_hygiene(subject: dict) -> RuleOutcome:
    gap = require(subject, "columns")
    if gap:
        return gap
    candidates = [
        c
        for c in _visible(subject["columns"])
        if c.get("data_type") in ("int64", "double", "decimal")
        and c.get("semantic_role") in ("identifier", "code", "year", "month_number")
    ]
    if not candidates:
        return RuleOutcome.not_applicable("no non-additive numeric column detected")
    correct = [c for c in candidates if (c.get("summarize_by") or "").lower() == "none"]
    return graded(
        ratio(len(correct), len(candidates)),
        f"{len(correct)}/{len(candidates)} non-additive numeric columns set to summarizeBy=None",
        pass_at=1.0,
        observed={"incorrect": [c.get("name") for c in candidates if c not in correct][:25]},
        ev=evidence("scanner_api", "model.columns[].summarizeBy"),
    )


@registry.add(
    "SEM-014",
    "No duplicate or overlapping measures pollute the AI surface",
    M,
    Dimension.BUSINESS_SEMANTICS,
    Severity.MAJOR,
    "Consolidate duplicate measures, or differentiate them explicitly in name, description and AI instructions.",
    effort=Effort.M,
    owner_role="Data Modeler",
    docs=DOCS_AGENT_MODEL,
)
def duplicate_measures(subject: dict) -> RuleOutcome:
    gap = require(subject, "measures")
    if gap:
        return gap
    measures = _visible(subject["measures"])
    if not measures:
        return RuleOutcome.not_evaluated("no visible measure returned by the scan")
    seen: dict[str, list[str]] = {}
    for measure in measures:
        expression = _normalize_dax(measure.get("expression") or "")
        if expression:
            seen.setdefault(expression, []).append(measure.get("name", "?"))
    duplicates = {expr: names for expr, names in seen.items() if len(names) > 1}
    duplicated_names = [n for names in duplicates.values() for n in names]
    return graded(
        ratio(len(measures) - len(duplicated_names), len(measures)),
        f"{len(duplicates)} duplicated expression group(s) across {len(duplicated_names)} measures",
        pass_at=1.0,
        observed={"duplicate_groups": [names for names in duplicates.values()][:10]},
        ev=evidence("scanner_api", "model.measures[].expression"),
    )


@registry.add(
    "SEM-015",
    "Row-level security is enforced when the data requires it",
    M,
    Dimension.SECURITY,
    Severity.BLOCKING,
    "Define and test RLS roles; an agent inherits the caller's permissions but cannot invent a filter that does not exist.",
    weight=2.0,
    effort=Effort.L,
    owner_role="Security Owner",
)
def row_level_security(subject: dict) -> RuleOutcome:
    gap = require(subject, "rls_required", "rls_roles")
    if gap:
        return gap
    if not subject["rls_required"]:
        return RuleOutcome.not_applicable("data classification does not require row-level security")
    roles = subject["rls_roles"] or []
    if not roles:
        return RuleOutcome.failed(
            "row-level security is required but no role is defined",
            evidence=evidence("scanner_api", "model.roles"),
        )
    untested = [r.get("name") for r in roles if not r.get("tested")]
    if untested:
        return RuleOutcome.partial(
            0.5,
            f"{len(untested)}/{len(roles)} RLS roles have never been validated with a test persona",
            observed={"untested": untested},
            evidence=evidence("scanner_api", "model.roles"),
        )
    return RuleOutcome.passed(
        f"{len(roles)} RLS roles defined and tested",
        evidence=evidence("scanner_api", "model.roles"),
    )


@registry.add(
    "SEM-016",
    "Data freshness meets the declared SLA",
    M,
    Dimension.PERFORMANCE,
    Severity.MAJOR,
    "Fix the refresh schedule or the failing pipeline; agents must not answer from stale data.",
    effort=Effort.M,
    owner_role="Data Engineer",
)
def data_freshness(subject: dict) -> RuleOutcome:
    gap = require(subject, "hours_since_refresh", "freshness_sla_hours")
    if gap:
        return gap
    sla = subject["freshness_sla_hours"]
    if not sla or sla <= 0:
        return RuleOutcome.not_evaluated("no freshness SLA declared for this model")
    age = subject["hours_since_refresh"]
    if age <= sla:
        return RuleOutcome.passed(
            f"last refresh {age}h ago, within the {sla}h SLA",
            observed={"age_hours": age, "sla_hours": sla},
            evidence=evidence("fabric_rest", "model.refreshHistory"),
        )
    return RuleOutcome.failed(
        f"last refresh {age}h ago, beyond the {sla}h SLA",
        observed={"age_hours": age, "sla_hours": sla},
        evidence=evidence("fabric_rest", "model.refreshHistory"),
    )


@registry.add(
    "SEM-017",
    "Schema metadata was fully retrieved",
    M,
    Dimension.COVERAGE,
    Severity.MAJOR,
    "Refresh or republish the model so the scanner can return its sub-metadata, then re-assess.",
    weight=1.5,
    effort=Effort.S,
    owner_role="Platform Engineer",
    docs="https://learn.microsoft.com/fabric/governance/metadata-scanning-run",
)
def schema_retrieval(subject: dict) -> RuleOutcome:
    gap = require(subject, "schema_retrieval_error")
    if gap:
        return gap
    error = subject["schema_retrieval_error"]
    if not error:
        return RuleOutcome.passed(
            "model sub-metadata retrieved without error",
            evidence=evidence("scanner_api", "model.schemaRetrievalError"),
        )
    return RuleOutcome.failed(
        f"schema retrieval error: {error}; downstream rules are unreliable",
        observed={"error": error},
        evidence=evidence("scanner_api", "model.schemaRetrievalError"),
    )
