# Interpreting Results

You have just run the assessment and a screen of numbers came back. This guide is how to
read it, in the order that leads to a decision.

It is operational, not normative. [`docs/SCORING.md`](./SCORING.md) is the contract — it
owns the thresholds, the caps, the coverage floor and the rollup arithmetic, and it wins
on any disagreement. [`docs/RULES.md`](./RULES.md) is the generated catalogue — it owns
what each rule checks, its severity and its remediation. This document only explains how
to act on what the tool printed.

Everything below was reproduced on **2026-09-23** against ruleset `2026.09.1` (65 rules)
with:

```bash
python assess.py --inventory examples/sample_tenant --review --out artifacts
```

The excerpts are from the synthetic `examples/sample_tenant` fixture. Your run will show
your own objects; the shape is identical.

---

## 1. The reading order

The console prints the sections in the order you should read them, and it says so in its
own header:

```
HOW TO READ THIS
------------------------------------------------------------------------------
  1. Blocking findings (11) come first.
     They are walls, not quality issues - nothing ships until they clear.
  2. NOT EVALUATED (1) is a blind spot, not a bad score.
     Fix it by collecting more evidence, never by re-scoring.
  3. A score only means something beside its coverage and confidence.
     Eligibility, score and confidence are three results and are never merged.
  Full guide: docs/INTERPRETING_RESULTS.md
```

In full:

1. **Blocking findings first.** A tenant switch that is off, an ineligible capacity, a
   Pro workspace, an agent with one source too many, a report bound to a model that is
   not there — these are walls. No amount of metadata polish moves an object past them,
   so no discussion of quality is useful until they are cleared.
2. **`NOT_EVALUATED` objects second.** These are blind spots, not bad objects. Decide
   whether to improve collection *before* interpreting anything else, because everything
   downstream is drawn from the evidence you did not manage to collect.
3. **Scores third, and never without their confidence.** The score answers "how well
   prepared", the confidence answers "how much of it did we actually see". Quoting one
   without the other is the most common way this output gets misused.
4. **Backlog last.** It is already grouped by owner role and sorted by priority; it is
   the output you hand to people, not the output you argue about.

---

## 2. What each part of the console means

### The run header

```
Run       : run_20260923T150012Z
Tenant    : contoso-tenant
Ruleset   : 2026.09.1
Collector : offline
```

`Ruleset` and `Collector` are the two lines people skip and then regret. Scores are only
comparable between runs of the **same ruleset version**
([SCORING.md § Ruleset Versioning](./SCORING.md#ruleset-versioning)), and `offline` means
the verdict came from a supplied inventory, not from a tenant you just read.

### The per-object tables

```
SEMANTIC_MODEL (3)
------------------------------------------------------------------------------
 SCORE  STATUS                 COV  CONF  NAME
    NE  NOT EVALUATED          6%    0%  Churn Sandbox
  11.1  NOT READY             93%   91%  FIN_PNL_CONSO
  97.9  READY                 94%   93%  Sales Star Model
```

| Column | Read it as |
|--------|-----------|
| `SCORE` | The published 0–100 score, **after** any severity cap. `NE` means the object was not published — see §4. |
| `STATUS` | The readiness class for that score ([SCORING.md § Status Thresholds](./SCORING.md#status-thresholds)). |
| `COV` | Share of applicable rule weight the tool could actually evaluate. |
| `CONF` | Confidence: coverage blended with whether the findings carry reproducible evidence. |

Two habits worth forming:

- Read the row **right to left**: name, confidence, coverage, then the score. The score is
  the last thing that means anything.
- Eligibility is not a console column. It is in the JSON (`eligible`) and in the HTML
  report; on the console, `NOT READY` next to a blocking finding is the same statement.

### Blocking findings

```
BLOCKING FINDINGS (11)
------------------------------------------------------------------------------
  [AGT-002] Finance Copilot Agent: Source count stays within the documented limit
      6 sources exceed the documented maximum of 5
```

Rule ID, object, what the rule checks, then the observed fact. Take the rule ID to
[`docs/RULES.md`](./RULES.md) for the owner role, the effort estimate and the
remediation wording — this guide deliberately does not restate them, because that table
is generated from the engine and this one would go stale.

The header count is the truth; the console lists only the **first 20** blocking findings.
If the heading says more than 20, the rest are in the run's `*_assessment.json`
(`blocking_findings`) and in the HTML report.

### Remediation backlog

```
REMEDIATION BACKLOG (58 items, 11 blocking, 216.25 estimated days)
------------------------------------------------------------------------------
 !  200.0  Contoso                      TEN-006  [M] Compliance Officer
      Either co-locate the agent and its data, or obtain and record formal approval for cross-geo processing and storage.
```

The leading `!` marks an item that comes from a blocking finding (`blocks_go_live` in the
JSON and CSV). The number is the computed priority, which blends severity, the blast
radius of the object type and the effort — so a cheap fix on a high-leverage object can
outrank an expensive fix on a bigger finding. `[M]` is the effort class and the last
column is the **owner role**: the backlog is routed by role precisely so that nobody has
to triage it by hand.

Two things to know before you quote this block:

- The console prints only the **top 10** items. The counts in the heading cover the whole
  backlog; the full list is in `*_backlog.csv` / `*_backlog.json`.
- The estimated days are indicative person-days per effort class, meant for capacity
  planning. They are a sizing convention, not a measured delivery forecast.

### Preceptorship review (`--review` only)

```
PRECEPTORSHIP REVIEW
============================================================
Verdict: APPROVED
Cycles:  1
  evidence_completeness        ****  4.35
```

This scores **the assessment, not the tenant**. A low `evidence_completeness` or
`rule_coverage` means *your run* is thin, and it is a reason to go back to collection
before you present anything. An escalated verdict is what `--fail-on-review` (exit code
3) turns into a pipeline signal.

---

## 3. Triage table

| What you see | Likely cause | First move |
|--------------|--------------|-----------|
| Score at the blocking cap (39), `eligible = false`, status `NOT READY` | One or more blocking rules failed; the cap replaced the weighted score | Read that object's blocking findings. Nothing else about the object matters yet. |
| Score **below** the blocking cap with blocking findings | The object scored badly on its own merits *and* hit a wall | Same first move — but expect metadata debt after the wall is cleared, not a clean object. |
| `NE` / `NOT EVALUATED` | Coverage under the publication floor and no blocking finding: too little was readable to publish a verdict | Fix collection, then re-run. **Do not re-score the same evidence** — see §4. |
| Score roughly 50–70 with high confidence | Genuine, well-observed metadata debt — this is the normal state of a real estate | Work the backlog by owner role. This is the case the tool is built to serve. |
| High score with low confidence | You are looking at a guess with a confident font | Say so out loud. Publish the coverage next to the score, or publish neither. |
| Score capped at 59, status `REMEDIATION` | Major findings capped an otherwise higher raw score | Compare `score` and `raw_score` in the JSON; the gap is what remediation buys back. |

The middle rows are judgement calls that this project has found useful, not engine
behaviour. The rows about caps and the publication floor are engine behaviour, defined in
[SCORING.md § Severity Caps](./SCORING.md#severity-caps) and
[§ Coverage Floor](./SCORING.md#coverage-floor).

---

## 4. `NOT_EVALUATED` is an instruction, not a grade

`NOT_EVALUATED` says *we could not look*. It is not a failure and it is not a zero.
There is exactly one correct response: **improve collection and run again. Do not
re-score the same evidence, and never re-run "until it publishes".**

What the engine actually does:

- An object under the coverage floor is published with status `NOT_EVALUATED` and
  `eligible = false`. Being unreadable is not an endorsement.
- Its score is kept in the artifacts rather than blanked, so you can still see which
  rules did run — which is exactly why it must never be quoted alone. Reproduced on a
  deliberately thin model: **score 100.0, status `not_evaluated`, coverage 16%,
  confidence 0.2%**. A `100` beside `NE` means "the handful of rules we could read
  passed", not "excellent".
- A **blocking finding is conclusive even under the floor**: an observed wall is still
  published as `NOT_READY`, with a note saying so. Thin evidence means we cannot judge
  quality; it never means the wall stopped existing.

To find out *what* was unreadable, open the run's `*_assessment.json` — each scorecard
carries every finding, and an unevaluated one names the input it wanted:

```bash
python -c "import json,sys; d=json.load(open(sys.argv[1], encoding='utf-8')); [print(c['object_name'], f['rule_id'], f['outcome']['detail']) for c in d['scorecards'] for f in c['findings'] if f['outcome']['status']=='not_evaluated']" artifacts/<run-id>_assessment.json
```

Typical output is `missing evidence: evaluation` or `missing evidence: data_sources` —
the name of the field the collector did not supply. That is your collection backlog.

A worked example you will meet immediately: a Data Agent supplied without an evaluation
block returns `NOT_EVALUATED` for `AGT-006` … `AGT-012` and `AGT-014`, each naming
`evaluation` among the inputs it wanted. The tool does not execute a question bank; the
corpus is an input you supply
([Known limitations §3](./KNOWN_LIMITATIONS.md#3-agent-quality-is-declared-not-measured)).

---

## 5. Rules that surprise people

Six results that generate the most pushback in a readout, and what to answer.

**An agent that never refuses is more dangerous than one that answers less.** One
confident fabrication destroys trust in every correct answer before it. That is why
`AGT-011` is blocking and requires *evidence* that the agent declined an out-of-scope or
adversarial prompt — an untested refusal path is not a refusal path.

**Agent-level instructions do not influence DAX generation for a Power BI source.**
When an agent answers wrongly over a semantic model, coaching the agent prompt is the
intuitive fix and the wrong one: fix the **model metadata** — names, descriptions,
synonyms, explicit measures, AI instructions on the model. This is product behaviour the
ruleset encodes as guidance, not something the tool measures, and the catalogue is built
around it: `AGT-007`'s remediation says failed query generation usually signals ambiguous
model metadata rather than an agent defect, `AGT-003` makes an agent depend on the
readiness of the model beneath it, and `REP-004` exists because logic left in the report
layer is invisible to Copilot.

**An over-broad AI data schema is a problem, not generosity.** Exposing everything
widens the search space and lowers precision. `SEM-008` fails outright when no AI data
schema is configured ("the whole model is exposed to Copilot") **and** degrades to a
partial result when the schema exposes more than 80% of visible objects ("scoping is too
broad"). Selecting fewer, better objects scores higher than selecting all of them.

**"Approved for Copilot" is self-attestation, not proof of quality.** It is set by the
content author and expresses intent. No rule in this catalogue reads an endorsement,
certification or promotion flag — a badge cannot move a score here, by design
([Known limitations §7](./KNOWN_LIMITATIONS.md#7-endorsement-is-not-evidence)).
Related and equally unpopular: a report is not individually approved for Copilot; the
approval rides on the semantic model, so report rules score context and validation
surface.

**Missing evidence is never a pass.** An unreadable rule returns `NOT_EVALUATED`: it
lowers coverage and confidence and contributes neither a pass nor a zero to the score,
and an object read too thinly is published with the status `NOT_EVALUATED` instead of a
verdict. See §4 — this is the behaviour most likely to be "helpfully" argued away in a
meeting.

**A cap only ever lowers a score.** An object with a blocking finding is capped, but a
capped object may sit far below the cap on its own merits — in the sample run,
`Finance Copilot Agent` scores **18.9** with six blocking findings, not 39. Do not read a
cap as a floor.

---

## 6. Where the detail lives

`--out` writes, per run:

| File | Use it for |
|------|-----------|
| `<run-id>_assessment.json` | Everything: per-object `score`, `raw_score`, `status`, `eligible`, `coverage`, `confidence`, `dimension_scores`, `notes`, and every finding |
| `<run-id>_readiness.html` | The readout you share; same orientation block, plus per-object tables and the backlog |
| `<run-id>_backlog.json` / `.csv` | The work, routed by owner role |
| `<run-id>_review.json` | The preceptorship verdict (`--review`) |

The `notes` array is the fastest explanation of a surprising number. Real examples from
the sample run:

```
Sales Ops Detail        2 major finding(s) cap the score at 59: REP-004, REP-006
Finance Copilot Agent   6 blocking finding(s) cap the score at 39: AGT-002, AGT-008, ...
Churn Sandbox           coverage 6% below the 50% publication floor
Contoso                 rolled up from 3 workspaces (mean 59.3/100, coverage 82%)
```

If a parent score looks better than the children under it, read its notes: a child with a
blocking finding caps its parent, and children with status `NOT_EVALUATED` are excluded
from the aggregate rather than averaged in
([SCORING.md § Rollups](./SCORING.md#rollups)).

Exit codes (`0`, `1`, `2` with `--fail-on-blocking`, `3` with `--fail-on-review`) are
documented in the [README](../README.md), under "Exit Codes".

---

## 7. Before you present this

- Quote the three results together: eligibility, score, confidence. Never one alone.
- State coverage before quoting a tenant-level verdict. "68% of the estate was readable"
  changes how every number after it is heard.
- Quote thresholds from [`docs/RULES.md`](./RULES.md) and the engine, not from memory or
  from a chat transcript.
- Say what the run could not see. A Data Agent scored without an evaluation corpus, a
  live run whose field coverage is partial, a product limit that may have moved since the
  ruleset was pinned — all of it is catalogued in
  [`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md), and stating it is what makes the
  rest of the readout credible.
- Do not let the tool "fix" anything. It is strictly read-only; every remediation is a
  backlog item with a human owner.

---

Last reproduced against the engine on **2026-09-23**, ruleset `2026.09.1`, 65 rules.
