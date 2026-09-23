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
python assess.py --inventory examples/sample_tenant --review --out artifacts
```

`--inventory` takes a normalized inventory JSON file or a fixture folder. Add
`--fail-on-blocking` (exit 2) or `--fail-on-review` (exit 3) in a pipeline.

`--live` collection against a real tenant exists (`--tenant-id`, `--bearer-token-env`),
but only the transport and selected field mappings are live-validated. Read
[Known limitations §1](../../../docs/KNOWN_LIMITATIONS.md#1-live-collection-is-a-foundation-with-partial-field-validation)
before presenting a live run as a complete tenant inventory.

### 2. Read the results in this order

The console prints score, status, coverage and confidence per object, then a
`BLOCKING FINDINGS` section, then the backlog. Read it as:

1. **Blocking findings first** — walls, not quality issues. A tenant switch off, an
   ineligible capacity, a Pro workspace, an agent with six sources: no metadata polish
   changes the outcome until they are cleared.
2. **`NOT_EVALUATED` objects second** — blind spots, not bad objects. Fix collection,
   **do not re-score**.
3. **Scores third**, always alongside confidence.
4. **Backlog last** — grouped by owner role, sorted by priority.

The human-facing operational guide is
[`docs/INTERPRETING_RESULTS.md`](../../../docs/INTERPRETING_RESULTS.md): console columns,
the full triage table, the artifacts to open, and the worked examples. This Skill
summarises it. When the two differ, the guide and the engine win — prefer routing a user
there over paraphrasing from here, since it works without loading this Skill.

### 3. Report honestly

State coverage. If a third of the estate could not be read, say so before quoting a
tenant-level score.

## What To Check, By Level

> Every number below is the value **encoded by ruleset `2026.09.1`**, not an
> independently re-verified product fact. [`docs/RULES.md`](../../../docs/RULES.md) is
> the generated source of truth for the rules, their severities and their thresholds —
> when it disagrees with this summary, it wins. Source links and verification status for
> each product limit are tracked in
> [Known limitations §8 — Product Limits Age](../../../docs/KNOWN_LIMITATIONS.md#8-product-limits-age):
> on **2026-09-23** each linked source page resolved, but line-by-line product-fact
> re-verification is still open. Do not quote a limit from this Skill as a Microsoft
> fact; quote it as what the ruleset encodes.

**Tenant** — Fabric and Copilot switches scoped to the right security groups, an
eligible capacity (**F2+ / P1+**, the floor encoded by `TEN-004` / `WKS-001`; source
candidate link resolved 2026-09-23, fact verification open), healthy and unthrottled
capacity, cross-geo consent, scanner enabled with a dedicated service principal,
sensitivity labels, named owners.

**Workspace** — capacity-backed (a Pro workspace cannot host an agent), governance
metadata, lifecycle separation, named owners.

**Semantic model** — star schema, business-meaningful names, descriptions whose first
**200 characters** carry the meaning (`DESCRIPTION_BUDGET`), synonyms, an AI data schema
that is scoped rather than exhaustive and has no missing dependency, AI instructions
within **10,000 characters** (`AI_INSTRUCTIONS_MAX`), verified answers that are not
broken, tested RLS, fresh data, retrievable schema.

**Report** — business purpose stated, useful measures exposed, connected to a scored
model, maintained. A report is not individually approved for Copilot; the approval rides
on the model.

**Data Agent** — at most **5 data sources** (`MAX_DATA_SOURCES`), all reachable and
described, instructions present, use case compatible with a read-only **25×25** result
surface (`MAX_RESULT_ROWS` × `MAX_RESULT_COLUMNS`), and measured behaviour:
≥ **85%** accuracy (`MIN_ACCURACY`), ≥ **95%** on critical questions
(`MIN_CRITICAL_ACCURACY`), zero leakage, at least two personas tested, correct refusal
of out-of-scope questions. The accuracy thresholds are this project's own bar, not a
product limit. The tool does **not** execute a corpus: the evaluation block is supplied
as input, and without it `AGT-006` … `AGT-012` return `NOT_EVALUATED`
([Known limitations §3](../../../docs/KNOWN_LIMITATIONS.md#3-agent-quality-is-declared-not-measured)).

## Rules That Surprise People

Short forms of the six results that generate the most pushback. Each is explained, with
its rule IDs and the evidence behind it, in
[`docs/INTERPRETING_RESULTS.md` § Rules that surprise people](../../../docs/INTERPRETING_RESULTS.md#5-rules-that-surprise-people)
— route the user there rather than expanding from memory.

- **Missing evidence is never a pass.** An unreadable model is `NOT_EVALUATED`, not 100.
- **A blocking failure caps the score at 39** and revokes eligibility; a major failure
  caps at 59. A cap only ever lowers a score, so a capped object may score below 39.
  Weighted averages hide walls.
- **"Approved for Copilot" is self-attestation**, not proof of quality: no rule in the
  catalogue reads an endorsement flag.
- **An over-broad AI data schema is a problem**, not generosity: it widens the search
  space and lowers precision (`SEM-008` degrades past 80% exposure of visible objects).
- **Agent-level instructions do not influence DAX generation for a Power BI source** —
  fix the model metadata, not the agent prompt.
- **An agent that never refuses is more dangerous than one that answers less.** One
  confident fabrication destroys trust in every correct answer before it (`AGT-011`
  requires tested refusal).
- **Power BI Q&A: no rule depends on it, and this project has not verified a retirement
  date or its source.** Treat the timing as an unverified, changing product fact
  ([Known limitations §10](../../../docs/KNOWN_LIMITATIONS.md#10-retiring-dependencies)),
  do not quote a date from this Skill, and add no new dependency on Q&A.

## Interpreting A Low Score

| Pattern | Likely cause | First move |
|---------|--------------|------------|
| Score ≤ 39, eligible = false, status `NOT_READY` | A blocking rule failed | Read `blocking_findings`; nothing else matters yet |
| `NOT_EVALUATED` | Coverage below **50%** (`MIN_COVERAGE_TO_PUBLISH`) and no blocking finding — an observed wall is still published as `NOT_READY` | Fix collection, do not re-score |
| Score 50–70, high confidence | Genuine metadata debt | Work the backlog by owner |
| High score, low confidence | We are guessing | Say so; do not publish the score alone |

The two middle rows are triage judgement, not engine behaviour. The operator-facing
version of this table — with the console patterns, the capped-below-the-cap case and the
commands to find what went unread — is
[`docs/INTERPRETING_RESULTS.md` § Triage table](../../../docs/INTERPRETING_RESULTS.md#3-triage-table).

## Commands

```bash
python assess.py --list-rules                      # catalogue: 65 rules, ruleset 2026.09.1
python assess.py --inventory <dir> --review        # assess with quality review
python -m unittest discover -s tests -t .          # test suite
python scripts/check_agent_ownership.py            # module and documentation ownership
python scripts/check_evidence_sinks.py             # evidence sinks and identifier hygiene
python scripts/build_rules_doc.py --check          # fail if docs/RULES.md is stale
python scripts/build_rules_doc.py                  # regenerate docs/RULES.md
```

All of these run in CI. `check_agent_ownership.py` now covers both every module under
`fabric_iq/` and the documentation that carries a privacy, identity or retention claim —
this Skill is claimed by **@readme**. `check_evidence_sinks.py` asserts that every writer
destination resolves to a committed `.gitignore` rule, that no tracked file is shadowed
by those rules, and that no tracked file carries a real tenant identifier.

## Must

- Report score, eligibility and confidence together
- Name the blocking findings before discussing quality
- State coverage before quoting a tenant-level verdict
- Point the user at [`docs/INTERPRETING_RESULTS.md`](../../../docs/INTERPRETING_RESULTS.md)
  when they ask how to read a run — the repository must stay usable without this Skill
- Quote thresholds from `docs/RULES.md` and the engine constants, not from memory
- Treat every fixture and example as synthetic

## Avoid

- Merging the three results into one headline number
- Reporting `NOT_EVALUATED` as a low score
- Recommending an automated fix — this tool is strictly read-only
- Quoting a product limit without checking its date in `docs/KNOWN_LIMITATIONS.md`

## Reference

- [How to read a run](../../../docs/INTERPRETING_RESULTS.md) — the human-facing
  operational guide; it stands alone without this Skill and supersedes any summary here
- [Scoring contract](../../../docs/SCORING.md)
- [Rule catalogue](../../../docs/RULES.md) — generated; the source of truth for rules and thresholds
- [Known limitations](../../../docs/KNOWN_LIMITATIONS.md) — what this tool cannot see, and which limits are dated
- [Roadmap](../../../docs/ROADMAP.md)

Last reconciled against the engine on **2026-09-23**, ruleset `2026.09.1`, 65 rules.
