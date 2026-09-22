"""Report readiness rules.

A report is not approved for Copilot individually: approval is carried by its
semantic model. These rules therefore score the report as a *context and
validation surface* — the questions it answers, the clarity of its visuals and
the business logic it hides from the model.
"""

from __future__ import annotations

from fabric_iq.models import Dimension, Effort, ObjectType, RuleOutcome, Severity
from fabric_iq.rules.base import evidence, graded, ratio, registry, require

R = ObjectType.REPORT

#: Below this ratio a report is effectively unused and should not drive priorities.
MIN_MONTHLY_VIEWS = 5


@registry.add(
    "REP-001",
    "Report binds to an accessible semantic model",
    R,
    Dimension.ARCHITECTURE,
    Severity.BLOCKING,
    "Rebind the report to a reachable semantic model, or retire the report.",
    weight=2.0,
    effort=Effort.S,
    owner_role="Report Owner",
)
def model_binding(subject: dict) -> RuleOutcome:
    gap = require(subject, "semantic_model_id", "semantic_model_reachable")
    if gap:
        return gap
    if not subject["semantic_model_id"]:
        return RuleOutcome.failed(
            "report has no semantic model binding",
            evidence=evidence("scanner_api", "report.datasetId"),
        )
    if not subject["semantic_model_reachable"]:
        return RuleOutcome.failed(
            f"bound model {subject['semantic_model_id']} is not reachable in the assessed scope",
            evidence=evidence("scanner_api", "report.datasetId"),
        )
    return RuleOutcome.passed(
        "report is bound to a reachable semantic model",
        evidence=evidence("scanner_api", "report.datasetId"),
    )


@registry.add(
    "REP-002",
    "Source semantic model is itself ready",
    R,
    Dimension.ARCHITECTURE,
    Severity.MAJOR,
    "Remediate the source model first; a report can never be more AI-ready than the model behind it.",
    weight=2.0,
    effort=Effort.XL,
    owner_role="Model Owner",
)
def source_model_readiness(subject: dict) -> RuleOutcome:
    gap = require(subject, "semantic_model_score")
    if gap:
        return gap
    score = subject["semantic_model_score"]
    if score is None:
        return RuleOutcome.not_evaluated("source model has not been scored in this run")
    return graded(
        ratio(float(score), 100.0),
        f"source semantic model scores {score:.0f}/100",
        pass_at=0.85,
        observed={"model_score": score},
        ev=evidence("assessment", "scorecards.semantic_model"),
    )


@registry.add(
    "REP-003",
    "Report contains no broken visual",
    R,
    Dimension.VISUAL_QUALITY,
    Severity.MAJOR,
    "Repair visuals referencing deleted or renamed fields before using the report as a Copilot reference.",
    weight=1.5,
    effort=Effort.M,
    owner_role="Report Owner",
)
def broken_visuals(subject: dict) -> RuleOutcome:
    gap = require(subject, "visual_count", "broken_visuals")
    if gap:
        return gap
    total = subject["visual_count"]
    if total <= 0:
        return RuleOutcome.not_evaluated("report definition returned no visual")
    broken = subject["broken_visuals"] or []
    return graded(
        ratio(total - len(broken), total),
        f"{len(broken)}/{total} visuals reference missing fields",
        pass_at=1.0,
        observed={"broken": broken[:25]},
        ev=evidence("fabric_rest", "report.definition.visuals"),
    )


@registry.add(
    "REP-004",
    "Business logic lives in the model, not in the report",
    R,
    Dimension.ARCHITECTURE,
    Severity.MAJOR,
    "Promote report-level measures into the semantic model; Copilot cannot see logic defined in the report layer.",
    weight=1.5,
    effort=Effort.L,
    owner_role="Report Owner",
)
def report_level_measures(subject: dict) -> RuleOutcome:
    gap = require(subject, "report_level_measures")
    if gap:
        return gap
    local = subject["report_level_measures"] or []
    if not local:
        return RuleOutcome.passed(
            "no report-level measure; all logic is reachable by Copilot",
            evidence=evidence("fabric_rest", "report.definition.measures"),
        )
    return RuleOutcome.failed(
        f"{len(local)} measure(s) defined in the report and invisible to Copilot",
        observed={"measures": local[:25]},
        evidence=evidence("fabric_rest", "report.definition.measures"),
    )


@registry.add(
    "REP-005",
    "Visual titles are explicit and unambiguous",
    R,
    Dimension.VISUAL_QUALITY,
    Severity.MINOR,
    "Replace default visual titles with business wording; they become the question phrasing users reuse with Copilot.",
    effort=Effort.M,
    owner_role="Report Owner",
)
def visual_titles(subject: dict) -> RuleOutcome:
    gap = require(subject, "visual_count", "untitled_visuals")
    if gap:
        return gap
    total = subject["visual_count"]
    if total <= 0:
        return RuleOutcome.not_evaluated("report definition returned no visual")
    untitled = subject["untitled_visuals"] or []
    return graded(
        ratio(total - len(untitled), total),
        f"{len(untitled)}/{total} visuals have a default or empty title",
        pass_at=0.9,
        observed={"untitled": untitled[:25]},
        ev=evidence("fabric_rest", "report.definition.visuals"),
    )


@registry.add(
    "REP-006",
    "Persistent filters do not contradict the visible context",
    R,
    Dimension.FUNCTIONAL_QUALITY,
    Severity.MAJOR,
    "Surface hidden report or page filters as visible slicers, or document them in the model AI instructions.",
    effort=Effort.M,
    owner_role="Report Owner",
)
def hidden_filters(subject: dict) -> RuleOutcome:
    gap = require(subject, "hidden_filters")
    if gap:
        return gap
    hidden = subject["hidden_filters"] or []
    if not hidden:
        return RuleOutcome.passed(
            "no hidden restrictive filter",
            evidence=evidence("fabric_rest", "report.definition.filters"),
        )
    return RuleOutcome.failed(
        f"{len(hidden)} hidden restrictive filter(s) silently change the numbers users see",
        observed={"filters": hidden[:25]},
        evidence=evidence("fabric_rest", "report.definition.filters"),
    )


@registry.add(
    "REP-007",
    "Report is accessible",
    R,
    Dimension.GOVERNANCE,
    Severity.MINOR,
    "Add alt text to visuals and verify contrast ratios.",
    effort=Effort.M,
    owner_role="Report Owner",
    docs="https://learn.microsoft.com/power-bi/create-reports/desktop-accessibility-creating-reports",
)
def accessibility(subject: dict) -> RuleOutcome:
    gap = require(subject, "visual_count", "visuals_with_alt_text")
    if gap:
        return gap
    total = subject["visual_count"]
    if total <= 0:
        return RuleOutcome.not_evaluated("report definition returned no visual")
    return graded(
        ratio(subject["visuals_with_alt_text"], total),
        f"{subject['visuals_with_alt_text']}/{total} visuals carry alt text",
        pass_at=0.8,
        ev=evidence("fabric_rest", "report.definition.visuals"),
    )


@registry.add(
    "REP-008",
    "Report has an owner and a declared audience",
    R,
    Dimension.GOVERNANCE,
    Severity.MAJOR,
    "Record the report owner and its audience so remediation has an addressee.",
    effort=Effort.XS,
    owner_role="Workspace Admin",
)
def report_ownership(subject: dict) -> RuleOutcome:
    gap = require(subject, "owner", "audience")
    if gap:
        return gap
    present = [k for k in ("owner", "audience") if subject.get(k)]
    return graded(
        ratio(len(present), 2),
        f"recorded: {', '.join(present) or 'nothing'}",
        pass_at=1.0,
        ev=evidence("governance_register", "report.owner"),
    )


@registry.add(
    "REP-009",
    "Report is actually consumed",
    R,
    Dimension.OPERATIONS,
    Severity.MINOR,
    "Deprioritise or retire unused reports rather than remediating them for Copilot.",
    effort=Effort.XS,
    owner_role="Report Owner",
)
def report_usage(subject: dict) -> RuleOutcome:
    gap = require(subject, "monthly_views")
    if gap:
        return gap
    views = subject["monthly_views"]
    if views >= MIN_MONTHLY_VIEWS:
        return RuleOutcome.passed(
            f"{views} views over the last 30 days",
            observed={"monthly_views": views},
            evidence=evidence("activity_events", "report.views"),
        )
    return RuleOutcome.failed(
        f"only {views} views over the last 30 days",
        observed={"monthly_views": views},
        evidence=evidence("activity_events", "report.views"),
    )


@registry.add(
    "REP-010",
    "Report questions are candidates for verified answers",
    R,
    Dimension.FUNCTIONAL_QUALITY,
    Severity.MINOR,
    "Promote the most consulted report pages into verified answers on the source model.",
    effort=Effort.M,
    owner_role="Model Owner",
)
def verified_answer_candidates(subject: dict) -> RuleOutcome:
    gap = require(subject, "verified_answer_candidates")
    if gap:
        return gap
    candidates = subject["verified_answer_candidates"] or []
    if not candidates:
        return RuleOutcome.failed(
            "no page identified as a verified-answer candidate",
            evidence=evidence("assessment", "report.candidates"),
        )
    return RuleOutcome.passed(
        f"{len(candidates)} verified-answer candidate(s) identified",
        observed={"candidates": candidates[:10]},
        evidence=evidence("assessment", "report.candidates"),
    )
