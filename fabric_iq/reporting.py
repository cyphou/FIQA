"""Console and HTML reporting for an assessment run."""

from __future__ import annotations

import html
import os
from typing import Any

from fabric_iq.errors import PersistenceError
from fabric_iq.models import (
    AssessmentRun,
    Finding,
    ObjectType,
    ReadinessStatus,
    Scorecard,
    Severity,
)
from fabric_iq.preceptor import ReviewReport
from fabric_iq.remediation import RemediationBacklog

STATUS_LABEL = {
    ReadinessStatus.READY: "READY",
    ReadinessStatus.READY_WITH_CONDITIONS: "READY (conditions)",
    ReadinessStatus.REMEDIATION_REQUIRED: "REMEDIATION",
    ReadinessStatus.NOT_READY: "NOT READY",
    ReadinessStatus.NOT_EVALUATED: "NOT EVALUATED",
}

STATUS_COLOR = {
    ReadinessStatus.READY: "#107c10",
    ReadinessStatus.READY_WITH_CONDITIONS: "#7a7a00",
    ReadinessStatus.REMEDIATION_REQUIRED: "#d18b00",
    ReadinessStatus.NOT_READY: "#a4262c",
    ReadinessStatus.NOT_EVALUATED: "#605e5c",
}

#: Soft pill (background, text) colors for the HTML report, FUAM/FCA-styled.
STATUS_BADGE = {
    ReadinessStatus.READY: ("#dff6ee", "#0b6d5c"),
    ReadinessStatus.READY_WITH_CONDITIONS: ("#fff4ce", "#7a6a00"),
    ReadinessStatus.REMEDIATION_REQUIRED: ("#fdead2", "#a95c00"),
    ReadinessStatus.NOT_READY: ("#fbe4e2", "#a4262c"),
    ReadinessStatus.NOT_EVALUATED: ("#eef0f2", "#5f6b73"),
}

SEVERITY_LABEL = {
    Severity.BLOCKING: "Blocking",
    Severity.MAJOR: "Major",
    Severity.MINOR: "Minor",
    Severity.INFO: "Info",
}

SEVERITY_BADGE = {
    Severity.BLOCKING: ("#fbe4e2", "#a4262c"),
    Severity.MAJOR: ("#fdead2", "#a95c00"),
    Severity.MINOR: ("#fff4ce", "#7a6a00"),
    Severity.INFO: ("#e6f1fb", "#0c5aa6"),
}

TYPE_ORDER = (
    ObjectType.TENANT,
    ObjectType.WORKSPACE,
    ObjectType.SEMANTIC_MODEL,
    ObjectType.REPORT,
    ObjectType.DATA_AGENT,
)

#: The human-facing guide. Both renderers point at it; neither depends on it.
INTERPRETATION_GUIDE = "docs/INTERPRETING_RESULTS.md"

ORIENTATION_TITLE = "HOW TO READ THIS"
ORIENTATION_HTML_TITLE = "How to read this report"


def _score_cell(card: Scorecard) -> str:
    if card.status is ReadinessStatus.NOT_EVALUATED:
        return "NE"
    return f"{card.score:5.1f}"


def _not_evaluated_count(run: AssessmentRun) -> int:
    return sum(
        1 for c in run.scorecards if c.status is ReadinessStatus.NOT_EVALUATED
    )


def _orientation_points(run: AssessmentRun) -> list[tuple[str, str]]:
    """The three things a first-time reader has to know, as (claim, why) pairs.

    Counts are surfaced here only so the reader learns, in the first screen, how
    many walls and how many blind spots this run has. Nothing is recomputed,
    merged or restated as a verdict.
    """
    blocking = len(run.blocking_findings)
    not_evaluated = _not_evaluated_count(run)
    if blocking:
        walls = (
            f"Blocking findings ({blocking}) come first.",
            "They are walls, not quality issues - nothing ships until they clear.",
        )
    else:
        walls = (
            "Blocking findings (0) come first.",
            "None today - no object is structurally excluded, so read the scores next.",
        )
    return [
        walls,
        (
            f"NOT EVALUATED ({not_evaluated}) is a blind spot, not a bad score.",
            "Fix it by collecting more evidence, never by re-scoring.",
        ),
        (
            "A score only means something beside its coverage and confidence.",
            "Eligibility, score and confidence are three results and are never merged.",
        ),
    ]


def _orientation_console(run: AssessmentRun) -> list[str]:
    lines = [ORIENTATION_TITLE, "-" * 78]
    for index, (claim, why) in enumerate(_orientation_points(run), start=1):
        lines.append(f"  {index}. {claim}")
        lines.append(f"     {why}")
    lines.append(f"  Full guide: {INTERPRETATION_GUIDE}")
    lines.append("")
    return lines


def _orientation_html(run: AssessmentRun) -> str:
    items = "".join(
        f"<li><strong>{html.escape(claim)}</strong> {html.escape(why)}</li>"
        for claim, why in _orientation_points(run)
    )
    return (
        '<section id="sec-orientation" class="card orient-card">'
        f"<h2>{html.escape(ORIENTATION_HTML_TITLE)}</h2>"
        f'<ol class="orient">{items}</ol>'
        f'<p class="orient-more">Full guide: <code>{html.escape(INTERPRETATION_GUIDE)}</code></p>'
        "</section>"
    )


def to_console(
    run: AssessmentRun,
    backlog: RemediationBacklog,
    review: ReviewReport | None = None,
) -> str:
    """Render the executive summary of a run."""
    lines: list[str] = [
        "",
        "FABRIC IQ READINESS",
        "=" * 78,
        f"Run       : {run.run_id}",
        f"Tenant    : {run.tenant_id}",
        f"Ruleset   : {run.ruleset_version}",
        f"Collector : {run.collector_mode}",
        "",
    ]
    lines.extend(_orientation_console(run))

    for object_type in TYPE_ORDER:
        cards = run.by_type(object_type)
        if not cards:
            continue
        lines.append(f"{object_type.value.upper()} ({len(cards)})")
        lines.append("-" * 78)
        lines.append(f"{'SCORE':>6}  {'STATUS':<20} {'COV':>5} {'CONF':>5}  NAME")
        for card in sorted(cards, key=lambda c: c.score):
            lines.append(
                f"{_score_cell(card):>6}  {STATUS_LABEL[card.status]:<20} "
                f"{card.coverage:>4.0%} {card.confidence:>5.0%}  {card.object_name}"
            )
        lines.append("")

    blocking = run.blocking_findings
    lines.append(f"BLOCKING FINDINGS ({len(blocking)})")
    lines.append("-" * 78)
    if not blocking:
        lines.append("  none")
    for finding in blocking[:20]:
        lines.append(f"  [{finding.rule_id}] {finding.object_name}: {finding.title}")
        lines.append(f"      {finding.outcome.detail}")
    lines.append("")

    lines.append(
        f"REMEDIATION BACKLOG ({len(backlog.items)} items, "
        f"{len(backlog.blocking_items)} blocking, {backlog.total_days} estimated days)"
    )
    lines.append("-" * 78)
    for item in backlog.top(10):
        flag = "!" if item.blocks_go_live else " "
        lines.append(
            f" {flag} {item.priority:6.1f}  {item.object_name:<28.28} "
            f"{item.rule_id}  [{item.effort.value}] {item.owner_role}"
        )
        lines.append(f"      {item.action}")
    lines.append("")

    if review is not None:
        lines.append(review.to_console())

    return "\n".join(lines)


def _html_table(headers: list[str], rows: list[list[str]], *, css_class: str = "") -> str:
    cls = f' class="{css_class}"' if css_class else ""
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    if not rows:
        body = f'<tr><td colspan="{len(headers)}" class="empty">No data.</td></tr>'
    return f"<table{cls}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _badge(text: str, bg: str, fg: str) -> str:
    return (
        f'<span class="badge" style="background:{bg};color:{fg}">{html.escape(text)}</span>'
    )


def _status_badge(status: ReadinessStatus) -> str:
    bg, fg = STATUS_BADGE[status]
    return _badge(STATUS_LABEL[status], bg, fg)


def _severity_badge(severity: Severity) -> str:
    bg, fg = SEVERITY_BADGE[severity]
    return _badge(SEVERITY_LABEL[severity], bg, fg)


def _kpi_card(value: str, label: str, *, tone: str = "brand") -> str:
    return (
        f'<div class="kpi kpi-{tone}"><div class="kpi-value">{value}</div>'
        f'<div class="kpi-label">{html.escape(label)}</div></div>'
    )


def _nav_pill(anchor: str, label: str, count: int | None = None) -> str:
    suffix = f' <span class="nav-count">{count}</span>' if count is not None else ""
    return f'<a class="nav-pill" href="#{anchor}">{html.escape(label)}{suffix}</a>'


def _section(anchor: str, title: str, subtitle: str, body: str, *, tone: str = "") -> str:
    cls = f"card {tone}".strip()
    sub = f'<p class="card-subtitle">{subtitle}</p>' if subtitle else ""
    return (
        f'<section id="{anchor}" class="{cls}">'
        f'<h2>{html.escape(title)}</h2>{sub}{body}</section>'
    )


def _blocking_findings_html(run: AssessmentRun) -> str:
    blocking = run.blocking_findings
    if not blocking:
        return '<p class="empty">No blocking findings — nothing is structurally impossible today.</p>'
    rows = "".join(
        f"""<div class="alert-row">
  <div class="alert-badge">{_severity_badge(Severity.BLOCKING)}</div>
  <div class="alert-body">
    <div class="alert-title">{html.escape(finding.object_name)} &middot;
      <code>{html.escape(finding.rule_id)}</code> &mdash; {html.escape(finding.title)}</div>
    <div class="alert-detail">{html.escape(finding.outcome.detail)}</div>
  </div>
</div>"""
        for finding in blocking[:25]
    )
    more = ""
    if len(blocking) > 25:
        more = f'<p class="empty">+{len(blocking) - 25} more blocking finding(s) — see the JSON export.</p>'
    return rows + more


def _object_type_section(run: AssessmentRun, object_type: ObjectType) -> str | None:
    cards = run.by_type(object_type)
    if not cards:
        return None
    eligible = sum(1 for c in cards if c.eligible)
    rows = []
    for card in sorted(cards, key=lambda c: c.score):
        rows.append(
            [
                html.escape(card.object_name),
                f'<strong>{_score_cell(card).strip()}</strong>',
                _status_badge(card.status),
                "Yes" if card.eligible else "No",
                f"{card.coverage:.0%}",
                f"{card.confidence:.0%}",
                str(len(card.blocking_findings)),
            ]
        )
    title = object_type.value.replace("_", " ").title()
    subtitle = f"{eligible}/{len(cards)} eligible"
    table = _html_table(
        ["Object", "Score", "Status", "Eligible", "Coverage", "Confidence", "Blocking"],
        rows,
        css_class="data-table",
    )
    return _section(f"sec-{object_type.value}", f"{title} ({len(cards)})", subtitle, table)


def _backlog_section(backlog: RemediationBacklog) -> str:
    rows = [
        [
            f"{item.priority:.0f}",
            _severity_badge(item.severity),
            html.escape(item.object_name),
            f"<code>{html.escape(item.rule_id)}</code>",
            html.escape(item.action),
            html.escape(item.owner_role or "Unassigned"),
            item.effort.value.upper(),
            f"{item.estimated_days:g}",
        ]
        for item in backlog.top(50)
    ]
    table = _html_table(
        ["Priority", "Severity", "Object", "Rule", "Action", "Owner", "Effort", "Days"],
        rows,
        css_class="data-table",
    )
    subtitle = (
        f"{len(backlog.items)} item(s) &middot; {len(backlog.blocking_items)} block go-live "
        f"&middot; {backlog.total_days:g} estimated person-days &middot; top {min(50, len(backlog.items))} shown"
    )
    return _section("sec-backlog", "Remediation backlog", subtitle, table)


def _preceptor_section(review: ReviewReport) -> str:
    final = review.final
    rows = []
    for dimension, score in final.scores.items():
        filled = int(round(score))
        stars = "★" * filled + "☆" * (5 - filled)
        rows.append([html.escape(dimension), f"{score:.1f} / 5", f'<span class="stars">{stars}</span>'])
    table = _html_table(["Dimension", "Score", ""], rows, css_class="data-table")
    verdict_tone = "ok" if review.verdict == "approved" else "warn"
    subtitle = (
        f'Verdict: {_badge(review.verdict.upper(), *(STATUS_BADGE[ReadinessStatus.READY] if verdict_tone == "ok" else STATUS_BADGE[ReadinessStatus.REMEDIATION_REQUIRED]))}'
        f" &middot; average {final.average()} / 5.0"
    )
    return _section("sec-preceptor", "Preceptorship review", subtitle, table)


def to_html(
    run: AssessmentRun,
    backlog: RemediationBacklog,
    review: ReviewReport | None = None,
    path: str | None = None,
) -> str:
    """Render a standalone HTML readiness report, styled after Microsoft's FUAM/FCA
    Fabric Toolbox reports (teal branding, KPI stat cards, section navigation, soft
    status pills) but adapted for a single static, offline, script-free HTML file."""
    present_types = [t for t in TYPE_ORDER if run.by_type(t)]
    all_cards = run.scorecards
    evaluated = [c for c in all_cards if c.status is not ReadinessStatus.NOT_EVALUATED]
    not_evaluated = len(all_cards) - len(evaluated)
    eligible = sum(1 for c in all_cards if c.eligible)
    avg_score = sum(c.score for c in evaluated) / len(evaluated) if evaluated else 0.0
    avg_confidence = sum(c.confidence for c in all_cards) / len(all_cards) if all_cards else 0.0
    blocking = run.blocking_findings

    kpis = "".join(
        [
            _kpi_card(str(len(all_cards)), "Objects assessed"),
            _kpi_card(f"{eligible}/{len(all_cards) or 0}", "Eligible objects"),
            _kpi_card(f"{avg_score:.0f}", "Average score (evaluated)"),
            _kpi_card(f"{avg_confidence:.0%}", "Average confidence"),
            _kpi_card(str(len(blocking)), "Blocking findings", tone="danger" if blocking else "ok"),
            _kpi_card(str(not_evaluated), "Not evaluated", tone="warn" if not_evaluated else "brand"),
            _kpi_card(str(len(backlog.items)), "Backlog items"),
            _kpi_card(f"{backlog.total_days:g}d", "Estimated remediation effort"),
        ]
    )

    nav_items = [
        _nav_pill("sec-orientation", "How to read this"),
        _nav_pill("sec-blocking", "Blocking findings", len(blocking)),
    ]
    for object_type in present_types:
        nav_items.append(
            _nav_pill(f"sec-{object_type.value}", object_type.value.replace("_", " ").title(),
                       len(run.by_type(object_type)))
        )
    nav_items.append(_nav_pill("sec-backlog", "Backlog", len(backlog.items)))
    if review is not None:
        nav_items.append(_nav_pill("sec-preceptor", "Preceptorship"))

    sections = [
        _orientation_html(run),
        _section(
            "sec-blocking",
            "Blocking findings",
            "These are walls, not quality issues — nothing else matters until they clear.",
            _blocking_findings_html(run),
            tone="alert-card" if blocking else "",
        )
    ]
    for object_type in present_types:
        section_html = _object_type_section(run, object_type)
        if section_html:
            sections.append(section_html)
    sections.append(_backlog_section(backlog))
    if review is not None:
        sections.append(_preceptor_section(review))

    document = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fabric IQ Readiness — {html.escape(run.tenant_id)}</title>
<style>
 :root {{
   --brand-dark: #0b4f43; --brand: #0f6d5c; --brand-light: #1a8a72;
   --bg: #f4f6f4; --card-bg: #ffffff; --border: #e3e5e1; --ink: #1b1f1e; --muted: #667066;
   --shadow: 0 1px 2px rgba(15,23,42,.06), 0 6px 16px rgba(15,23,42,.05);
   --radius: 14px;
 }}
 * {{ box-sizing: border-box; }}
 body {{
   font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
   margin: 0; color: var(--ink); background: var(--bg); line-height: 1.4;
 }}
 a {{ color: inherit; }}
 code {{ background: #eef1ef; border-radius: 4px; padding: .05rem .35rem; font-size: .85em; }}
 header.fiq-header {{
   background: linear-gradient(135deg, var(--brand-dark), var(--brand-light));
   color: #fff; padding: 1.6rem 2rem 2.2rem;
 }}
 .fiq-header-inner {{ max-width: 1180px; margin: 0 auto; display: flex; align-items: center; gap: 1rem; }}
 .fiq-logo {{ width: 40px; height: 40px; flex: none; }}
 .fiq-header h1 {{ margin: 0; font-size: 1.5rem; font-weight: 600; }}
 .fiq-header .meta {{ margin: .25rem 0 0; color: #d8efe9; font-size: .85rem; }}
 nav.fiq-nav {{
   position: sticky; top: 0; z-index: 5; background: #fff; border-bottom: 1px solid var(--border);
   box-shadow: var(--shadow); overflow-x: auto; white-space: nowrap;
 }}
 .fiq-nav-inner {{ max-width: 1180px; margin: 0 auto; padding: .5rem 1.5rem; display: flex; gap: .5rem; }}
 .nav-pill {{
   text-decoration: none; font-size: .8rem; font-weight: 600; color: var(--brand-dark);
   background: #eef6f4; border: 1px solid #d9ece6; border-radius: 999px; padding: .3rem .75rem;
   flex: none;
 }}
 .nav-pill:hover {{ background: #dff0ea; }}
 .nav-count {{ color: var(--muted); font-weight: 400; }}
 main.fiq-wrap {{ max-width: 1180px; margin: -1.2rem auto 3rem; padding: 0 1.5rem; }}
 .kpi-grid {{
   display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .9rem;
   margin-bottom: 1.5rem;
 }}
 .kpi {{
   background: var(--card-bg); border-radius: var(--radius); box-shadow: var(--shadow);
   padding: 1rem 1.1rem; border-top: 3px solid var(--brand);
 }}
 .kpi-danger {{ border-top-color: #a4262c; }}
 .kpi-warn {{ border-top-color: #d18b00; }}
 .kpi-ok {{ border-top-color: #107c10; }}
 .kpi-value {{ font-size: 1.7rem; font-weight: 700; color: var(--ink); }}
 .kpi-label {{ font-size: .78rem; color: var(--muted); margin-top: .15rem; text-transform: uppercase; letter-spacing: .02em; }}
 .card {{
   background: var(--card-bg); border-radius: var(--radius); box-shadow: var(--shadow);
   padding: 1.2rem 1.4rem; margin-bottom: 1.3rem;
 }}
 .card h2 {{ margin: 0 0 .2rem; font-size: 1.1rem; color: var(--brand-dark); }}
 .card-subtitle {{ margin: 0 0 .8rem; font-size: .85rem; color: var(--muted); }}
 .alert-card {{ border-left: 4px solid #a4262c; }}
 .orient-card {{ border-left: 4px solid var(--brand); }}
 ol.orient {{ margin: .2rem 0 .6rem; padding-left: 1.2rem; font-size: .88rem; }}
 ol.orient li {{ margin-bottom: .25rem; color: var(--muted); }}
 ol.orient li strong {{ color: var(--ink); }}
 .orient-more {{ margin: 0; font-size: .82rem; color: var(--muted); }}
 table.data-table {{ border-collapse: collapse; width: 100%; font-size: .85rem; }}
 table.data-table th {{
   text-align: left; padding: .5rem .6rem; border-bottom: 2px solid var(--border);
   color: var(--muted); font-weight: 600; font-size: .75rem; text-transform: uppercase;
 }}
 table.data-table td {{ padding: .5rem .6rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
 table.data-table tr:hover td {{ background: #f7faf9; }}
 td.empty, p.empty {{ color: var(--muted); font-style: italic; }}
 .badge {{
   display: inline-block; border-radius: 999px; padding: .15rem .6rem; font-size: .75rem; font-weight: 600;
 }}
 .stars {{ color: var(--brand); letter-spacing: .1em; }}
 .alert-row {{ display: flex; gap: .8rem; padding: .6rem 0; border-bottom: 1px solid var(--border); }}
 .alert-row:last-child {{ border-bottom: none; }}
 .alert-title {{ font-weight: 600; font-size: .88rem; }}
 .alert-detail {{ color: var(--muted); font-size: .82rem; margin-top: .15rem; }}
 footer.fiq-footer {{ text-align: center; color: var(--muted); font-size: .78rem; padding: 1rem 0 2rem; }}
</style></head><body>
<header class="fiq-header"><div class="fiq-header-inner">
 <svg class="fiq-logo" viewBox="0 0 40 40" aria-hidden="true">
   <rect x="4" y="4" width="24" height="24" rx="6" fill="#ffffff" opacity=".28" transform="rotate(20 16 16)"/>
   <rect x="10" y="10" width="24" height="24" rx="6" fill="#ffffff" opacity=".85" transform="rotate(-10 22 22)"/>
 </svg>
 <div>
   <h1>Fabric IQ Readiness</h1>
   <p class="meta">Tenant {html.escape(run.tenant_id)} &middot; run {html.escape(run.run_id)}
    &middot; ruleset {html.escape(run.ruleset_version)} &middot; collector {html.escape(run.collector_mode)}
    &middot; completed {html.escape(run.completed_at)}</p>
 </div>
</div></header>
<nav class="fiq-nav"><div class="fiq-nav-inner">{''.join(nav_items)}</div></nav>
<main class="fiq-wrap">
<section class="kpi-grid">{kpis}</section>
{''.join(sections)}
</main>
<footer class="fiq-footer">Fabric IQ Readiness is a read-only assessment tool. Scores, eligibility and
 confidence are three independent results and must be read together — see docs/SCORING.md.</footer>
</body></html>"""

    if path:
        try:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(document)
        except OSError as exc:
            raise PersistenceError(f"cannot write {path}: {exc}") from exc
    return document
