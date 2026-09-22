---
name: fabric-iq-readiness
description: Assess whether a Power BI / Microsoft Fabric tenant and its objects (semantic models, reports, Fabric Data Agents) are ready for Fabric IQ and agentic experiences. Produces per-object eligibility, a 0-100 readiness score, a confidence level, and a prioritised remediation backlog. Use when the user wants to - (1) check if a tenant is ready for Fabric IQ or Copilot, (2) score semantic models for AI readiness, (3) assess a Fabric Data Agent before rollout, (4) find what blocks an agentic rollout, (5) produce a remediation plan for AI readiness. Triggers - "is my tenant ready for Fabric IQ", "AI readiness score", "Copilot readiness", "assess data agent", "prepare model for AI", "what blocks Fabric IQ", "readiness backlog".
---

# Fabric IQ Readiness Assessment

Evaluate a Power BI / Fabric estate for Fabric IQ and agentic readiness, and produce an
actionable remediation plan.

## When To Use This Skill

- "Is our tenant ready for Fabric IQ?"
- "Score our semantic models for AI readiness"
- "What do we need to fix before rolling out Data Agents?"
- "Why is this agent giving wrong answers?" (readiness triage, not debugging)

## Core Concept: Three Results, Never Merged

| Result | Question |
|--------|----------|
| **Eligibility** | Does anything make this structurally impossible? |
| **Score** (0–100) | How well prepared is it? |
| **Confidence** | How much could we actually observe? |

Never report a score without its confidence. A model scoring 92 on 35% coverage and one
scoring 92 on 98% coverage warrant opposite decisions.

## Workflow

### 1. Run the assessment

```bash
python assess.py --inventory <path-or-fixtures> --review --out artifacts
```

Add `--fail-on-blocking` (exit 2) or `--fail-on-review` (exit 3) in a pipeline.

### 2. Read the results in this order

1. **Blocking findings first.** These are walls, not quality issues. A tenant switch off,
   an ineligible capacity, a Pro workspace, an agent with six sources — no amount of
   metadata polish changes the outcome until they are cleared.
2. **`NOT_EVALUATED` objects second.** These are blind spots, not bad objects. Decide
   whether to improve collection before interpreting anything else.
3. **Scores third**, always alongside confidence.
4. **Backlog last** — grouped by owner role, sorted by priority.

### 3. Report honestly

State coverage. If a third of the estate could not be read, say so before quoting a
tenant-level score.

## What To Check, By Level

**Tenant** — Fabric and Copilot switches scoped to the right security groups, an
eligible capacity (F2+ / P1+), healthy and unthrottled capacity, cross-geo consent,
scanner enabled with a dedicated service principal, sensitivity labels, named owners.

**Workspace** — capacity-backed (a Pro workspace cannot host an agent), governance
metadata, lifecycle separation, named owners.

**Semantic model** — star schema, business-meaningful names, descriptions whose first
**200 characters** carry the meaning, synonyms, an AI data schema that is scoped rather
than exhaustive and has no missing dependency, AI instructions within **10,000
characters**, verified answers that are not broken, tested RLS, fresh data, retrievable
schema.

**Report** — business purpose stated, useful measures exposed, connected to a scored
model, maintained. A report is not individually approved for Copilot; the approval rides
on the model.

**Data Agent** — at most **5 data sources**, all reachable and described, instructions
present, use case compatible with a read-only **25×25** result surface, and measured
behaviour: ≥ 85% accuracy, ≥ 95% on critical questions, zero leakage, at least two
personas tested, correct refusal of out-of-scope questions.

## Rules That Surprise People

- **Missing evidence is never a pass.** An unreadable model is `NOT_EVALUATED`, not 100.
- **A blocking failure caps the score at 39.** Weighted averages hide walls.
- **"Approved for Copilot" is self-attestation**, not proof of quality.
- **An over-broad AI data schema is a problem**, not generosity: it widens the search
  space and lowers precision.
- **Agent-level instructions do not influence DAX generation for a Power BI source** —
  fix the model metadata, not the agent prompt.
- **An agent that never refuses is more dangerous than one that answers less.** One
  confident fabrication destroys trust in every correct answer before it.
- **Power BI Q&A retires in December 2026** — add no new dependency on it.

## Interpreting A Low Score

| Pattern | Likely cause | First move |
|---------|--------------|------------|
| Score 39, eligible = false | A blocking rule failed | Read `blocking_findings`; nothing else matters yet |
| `NOT_EVALUATED` | Coverage below 50% | Fix collection, do not re-score |
| Score 50–70, high confidence | Genuine metadata debt | Work the backlog by owner |
| High score, low confidence | We are guessing | Say so; do not publish the score alone |

## Commands

```bash
python assess.py --list-rules                      # the catalogue
python assess.py --inventory <dir> --review        # assess with quality review
python -m unittest discover -s tests -t .          # test suite
python scripts/check_agent_ownership.py            # agent ownership
python scripts/build_rules_doc.py                  # regenerate docs/RULES.md
```

## Must

- Report score, eligibility and confidence together
- Name the blocking findings before discussing quality
- State coverage before quoting a tenant-level verdict
- Treat every fixture and example as synthetic

## Avoid

- Merging the three results into one headline number
- Reporting `NOT_EVALUATED` as a low score
- Recommending an automated fix — this tool is strictly read-only
- Quoting a product limit without checking its date in `docs/KNOWN_LIMITATIONS.md`

## Reference

- [Scoring contract](../../../docs/SCORING.md)
- [Rule catalogue](../../../docs/RULES.md)
- [Known limitations](../../../docs/KNOWN_LIMITATIONS.md)
- [Roadmap](../../../docs/ROADMAP.md)
