# Scoring Contract

This document is normative. Any change to it requires a regression test in
`tests/test_scoring.py` and sign-off from `@scorer`.

## Three Results, Never Merged

Every scored object publishes three independent results:

| Result | Type | Meaning |
|--------|------|---------|
| **Eligibility** | boolean | Does the object clear every blocking rule? |
| **Readiness score** | 0–100 | How well prepared is it, across weighted dimensions? |
| **Confidence** | 0–100 | How much of it could we observe? |

The temptation to collapse these into one headline number is strong and must be
resisted. A model scoring 92 with 35% confidence and a model scoring 92 with 98%
confidence warrant opposite decisions. Merging them destroys precisely the information
that makes the assessment actionable.

## Rule Outcomes

| Outcome | Score contribution | Confidence contribution |
|---------|-------------------|------------------------|
| `PASSED` | 1.0 | counted |
| `PARTIAL(x)` | x (0 < x < 1) | counted |
| `FAILED` | 0.0 | counted |
| `NOT_EVALUATED` | none | **lowers coverage** |
| `NOT_APPLICABLE` | none | not counted either way |

The distinction between `FAILED` and `NOT_EVALUATED` is the backbone of the design.

- `FAILED` = we looked, and it is wrong.
- `NOT_EVALUATED` = we could not look.
- `NOT_APPLICABLE` = there was nothing to look at, by design.

Scoring an absence as failure invents findings that waste a remediation team's time.
Scoring it as success invents readiness that a business will act on. Both are worse
than declaring the blind spot.

## Dimensions

Rules are grouped into dimensions, weighted per object type in
`DIMENSION_WEIGHTS` (`fabric_iq/scoring.py`):

`architecture`, `business_semantics`, `ai_readiness`, `security`, `governance`,
`operations`, `coverage`, `quality`.

### Renormalization

Weights are renormalized over **the dimensions that produced at least one score**.

If security could not be read at all, the object is not given a security score of zero
(which slanders it) nor 100 (which endorses it). It is scored on what was observable,
and the unobservable part is reported as reduced confidence. This is the single most
important behaviour in the engine and it is covered by
`test_unobservable_dimension_lowers_confidence_not_score`.

## Severity Caps

| Severity | Cap | Eligibility |
|----------|-----|-------------|
| `BLOCKING` | 39 | revoked |
| `MAJOR` | 59 | preserved |
| `MINOR` | none | preserved |
| `INFO` | none | preserved |

Caps are one-directional: applying a cap may only **lower** a score. An object already
scoring 20 with a major failure stays at 20; it is not raised to 59. Any change that
allows a cap to raise a score is a defect.

The cap exists because weighted averages hide walls. An agent with five well-documented
sources and one unreachable source is not 83% ready — it does not run. The weighted
average would say 83; the cap says 39 and ineligible.

## Coverage Floor

```
coverage = evaluated_weight / applicable_weight
```

Coverage below **50%** forces status `NOT_EVALUATED`, regardless of score. Publishing a
verdict drawn from a third of the evidence is how a readiness programme loses its
credibility in a single meeting — and it only takes one.

"Regardless of score" includes the uncomfortable case: an object whose few readable rules
all passed carries a **high score and the status `NOT_EVALUATED`** — 100 is common. The
score is retained deliberately, because suppressing it would hide which rules did run.
Read the status first; a score is meaningless without the coverage that produced it.

## Status Thresholds

| Score | Status |
|-------|--------|
| ≥ 85 | `READY` |
| ≥ 70 | `READY_WITH_CONDITIONS` |
| ≥ 50 | `REMEDIATION_REQUIRED` |
| < 50 | `NOT_READY` |
| any, coverage < 50% | `NOT_EVALUATED` |

## Rollups

| Parent | Composition |
|--------|-------------|
| Workspace | 70% child objects, 20% own rules, 10% coverage |
| Tenant | 60% workspaces, 25% own rules, 15% coverage |

Two safeguards apply:

1. **A child with a blocking finding caps its parent at 59.** A workspace reporting
   green while containing an unusable model ends the conversation at exactly the point
   where it should have started.
2. **Children with status `NOT_EVALUATED` are excluded from the aggregate**, and the
   exclusion is noted on the parent. Averaging in an object we could not read would
   dilute the verdict with a number we did not measure.

## Confidence

Confidence combines coverage with evidence quality: how much of the applicable rule
weight was evaluated, and whether the findings carry reproducible evidence references.
It is reported alongside the score, never folded into it.

## Calibration Contract

The weights and thresholds above are **reasoned, not calibrated** — see
`docs/KNOWN_LIMITATIONS.md` §5. `fabric_iq/calibration.py` is the mechanism that
produces the evidence which could one day justify changing them. It is opt-in
(`assess.py --calibration`) and it changes no maths.

### What the mechanism guarantees

| Guarantee | Enforced by |
|---|---|
| The worksheet carries no verdict field | `assert_blinded`, called on every build, over the whole of `BLINDED_FIELDS` |
| Object names are pseudonymised, with no opt-out | `build_worksheet`; the mapping lives only in the key file |
| A fact quoting the engine's verdict on *another* object is dropped | `_quotes_a_verdict` — `semantic_model_score` and `source_scores` are the verdict one hop away |
| The draw is reproducible | `random.Random(seed)`; the seed is recorded in the key and the instruction sheet |
| The sample is bounded and stratified | `(object_type, band)` round-robin, default 24, roadmap band 20–30 |
| Row order does not encode the ranking | seeded shuffle, applied to rows *and* to pseudonym ordinals |

Blinding is structural, not cosmetic. A worksheet row cannot carry `score`,
`raw_score`, `status`, `eligible`, `confidence`, `coverage`, `dimension_scores`, or
any per-rule id, title, severity or outcome status — a rule id is a lookup key into
`docs/RULES.md`, where the severity is published, so handing over the id hands over
the cap, and the cap *is* the verdict.

One residual leak is accepted knowingly and documented rather than hidden: the
worksheet declares which evidence could **not** be observed, so a determined labeler
could count those lines and approximate coverage. Hiding them would make the
judgement uninformed, which is the worse failure. The verdict itself stays
unrecoverable.

### Agreement statistic

**Krippendorff's alpha with the ordinal difference function**, reported over the
readiness ladder, with exact percent agreement published beside it as a descriptive
companion and explicitly labelled chance-inflated.

Plain percent agreement over-credits chance: where four objects in five are
unhealthy, two labelers who both default to `not_ready` agree 80% of the time having
demonstrated nothing. Cohen's kappa corrects for chance but takes exactly two raters
and no blanks, and a returned worksheet realistically has two or three raters and a
few blanks. Alpha takes any number of raters, tolerates missing values by
construction, and — with the ordinal metric — counts `ready` vs
`ready_with_conditions` as a smaller disagreement than `ready` vs `not_ready`.
Unweighted statistics refuse to make that distinction, and on an ordinal ladder that
refusal is simply wrong.

**Inter-rater agreement is reported first**, before any comparison with the tool. If
two practitioners do not agree with each other, their disagreement with the tool
measures the labelling exercise, not the engine. The key order of the serialised
report is part of this contract and is tested.

Degenerate cases return `null` plus a reason, never a flattering number:

| Case | Reported |
|---|---|
| Fewer than two labelers | undefined — "agreement needs at least two independent labelers" |
| No unit carries two labels | undefined — "nothing is comparable" |
| Every label in the sample is the same class | undefined — "unmeasurable rather than perfect" |
| A labeler used one label throughout | alpha still computed, with a warning that it carries no discrimination |
| Missing or partial labels | excluded from the pairing, counted and warned; never imputed |
| A label outside the vocabulary | excluded and enumerated as a problem; never silently dropped |

Alpha is published raw, including negative values, which mean systematic
disagreement rather than "no agreement".

### `NOT_EVALUATED` in calibration

`insufficient_evidence` is the labeler's counterpart of `NOT_EVALUATED`, and it is
handled the same way the engine handles it: **it is not a rung on the ladder.**

- It has no entry in `ORDINAL_RANK`, so it can never be ranked below `not_ready`.
- Units where a voice said `insufficient_evidence` are held out of the ordinal
  comparison on both sides — labeler and tool alike.
- They are not discarded. They are analysed twice more: as a separate nominal
  "did the labelers agree about where the blind spots are" statistic over the whole
  sample, and as enumerated disagreements of kind `coverage`.

A divergence about whether an object *could be judged* is a different finding from a
divergence about whether it is *ready*, and merging them would quietly reintroduce
the "missing evidence is a bad score" error the engine exists to avoid.

### Every disagreement, enumerated

The roadmap requires "agreement and every disagreement". The report therefore
carries one record per diverging rater pair per object — labeler vs labeler and
labeler vs tool — with both labels, the ordinal distance, the kind, and the
rationales. A single aggregate that hid which objects diverged would fail the
requirement outright: the diverging row and its rationale are the only thing that
could ever justify a change to the maths.

### What calibration must never do

**It proposes no number.** No optimiser, no fitted weight, no recommended threshold.
`CalibrationReport.proposals` is empty by construction and tested to stay empty, and
a full round trip is tested to leave `DIMENSION_WEIGHTS`, `STATUS_THRESHOLDS`,
`SEVERITY_SCORE_CAP`, `MIN_COVERAGE_TO_PUBLISH` and both rollup maps byte-identical.
A routine that measured a disagreement *and* proposed the correction for it would
have stopped being evidence. Any weight or threshold change stays what it is today:
a human decision, with rationale, `@scorer` sign-off, a regression test in
`tests/test_scoring.py`, and ruleset-version handling.

### Privacy

A calibration sample drawn from a real tenant is customer data. The worksheet, the
instruction sheet, the key, the agreement report and the disagreement CSV are
evidence sinks exactly like `artifacts`, `lakehouse` and `powerbi_report`: written
only to a git-ignored destination (default `artifacts/calibration`), never
committed, and enumerated by `fabric_iq.calibration.calibration_sinks()` so
`scripts/check_evidence_sinks.py` can hold every one of them to a committed ignore
rule. **The key file is never handed to a labeler.**

## Ruleset Versioning

Every scorecard records `ruleset_version`. Scores are comparable across runs **only when
the ruleset version matches**. When product limits change and the catalogue changes with
them, a score shift may reflect the new ruleset rather than a real change in the estate.
Trend views must refuse to plot across incompatible versions rather than silently mixing
them and reporting an improvement nobody made.

### The policy: the token moves whenever the fingerprint moves

`ruleset_version` is the only comparability key a stored run carries, and stamping it is
an assertion — *"another run carrying this token was produced by the same scoring
inputs."* That assertion is now mechanically true rather than merely intended.

`fabric_iq.scoring.ruleset_fingerprint()` hashes a canonical list of **every input the
engine reads when it turns rule outcomes into a number**:

| Covered by the fingerprint | Not covered |
|---|---|
| The set of rule IDs | Rule titles and descriptions |
| Each rule's object type, dimension, severity and weight | Remediation prose, effort, owner role, doc links |
| `DIMENSION_WEIGHTS`, `SEVERITY_SCORE_CAP`, `STATUS_THRESHOLDS` | Rule registration order |
| `MIN_COVERAGE_TO_PUBLISH`, `WORKSPACE_ROLLUP`, `TENANT_ROLLUP` | Anything that cannot change a published number |

**The rule, stated so it cannot be got wrong by accident: if
`ruleset_fingerprint()` changes, `RULESET_VERSION` must change in the same commit, and a
new `RulesetRelease` must be appended to `RULESET_HISTORY`.**
`tests/test_scoring.py::TestRulesetIdentity` fails the build otherwise, and prints the
new fingerprint so the correct fix is the easy one.

Two properties of that rule are deliberate:

- **It is mechanical, not a judgement call.** The rejected alternative — *"bump only when
  scores actually become incomparable"* — asks a contributor to prove a negative about
  every estate the tool will ever be pointed at, at the end of the day they added the
  rule. The measured evidence against it is this repository: adding `SEM-018` and
  `REP-011` left the model score at 100.0 and looked score-neutral, while confidence moved
  0.9077 → 0.9121 and coverage 0.9231 → 0.9250 on an estate that had not changed. A rule
  that is inapplicable to the fixture is applicable to somebody's tenant. "Would this move
  a number anywhere?" is not answerable; "did the fingerprint move?" is.
- **Prose is free.** A fingerprint that moved on a typo fix would teach contributors to
  regenerate it reflexively, and a guard people regenerate without reading is decoration.
  Improving a remediation sentence costs nothing and must stay that way.

What the fingerprint **cannot** see is logic inside a rule's `check` — a threshold
constant such as `MIN_ACCURACY`, or a changed predicate. Hashing function bytecode would
fire on renamed locals and comment edits, which is the reflexive-regeneration failure
above. So that residue stays a human obligation, and it is a narrow one: **changing what a
rule decides is a ruleset increment exactly as much as adding the rule was.** Those
constants are already pinned by `tests/test_skill_drift.py`, so they cannot move quietly.

### Format

`YYYY.MM.N` — calendar year, zero-padded month, then a sequence number within that month
starting at 1. `2026.09.2` follows `2026.09.1`; the tenth increment in a month is
`2026.09.10`. Ordering is by the three numbers, never lexicographic. Versions are never
reused and never removed from the ledger.

### The ledger is append-only

`RULESET_HISTORY` is a record of what already happened. A shipped entry describes runs
that exist in somebody's Lakehouse today; editing one to match a changed catalogue
re-labels *their* evidence instead of versioning *ours*. Change the catalogue by appending
an entry — never by correcting an old one.

This one property is **reviewer-enforced, not machine-enforced**: a unit test sees the
ledger as it is, not as it was, so it cannot tell an appended entry from an edited one. A
diff that changes the fingerprint on an existing `RulesetRelease` instead of adding a new
one is re-labelling a baseline, and a reviewer must reject it.

### Migration: what the move to `2026.09.2` costs, and why it is the correct cost

`2026.09.1` was stamped on at least four different catalogues — 61 rules at first release,
then 63, 65 and 67 as `TEN-011`, `TEN-012`, `WKS-011`, `SEM-018` and `REP-011` were added
— because nothing tied the token to the catalogue. It therefore identifies no ruleset at
all, which is why its ledger entry carries `AMBIGUOUS_FINGERPRINT` instead of a hash. The
honest consequence, and the one a user will see:

1. **Every stored run stamped `2026.09.1` is now incomparable with new runs.**
   `select_comparable_history_runs` and `select_latest_baseline_run` default to
   `same_ruleset_only=True` and will skip them, so the first run after this change has **no
   baseline** and its trend section is empty. That is not a regression; those runs never
   were comparable with each other either, and the empty trend view is the first honest
   thing this tool has said about them.
2. **The next run establishes the new baseline.** From the second `2026.09.2` run onward,
   trends work normally and every comparison is between two runs of the same catalogue.
3. **Nothing needs re-running and nothing is deleted.** Stored runs, marts and reports load
   unchanged; only their comparability changed, and only to what was always true.
4. **If you must look across the boundary**, pass `same_ruleset_only=False` and read the
   result as a ruleset delta, not an estate delta. `compare_runs` already classifies every
   object as `RULESET_CHANGED` with "do not compare scores without migration notes", and
   that classification is the answer, not an obstacle to route around.

A score comparison is only as good as its comparability key. Prior to this change, ours
was a constant.

## Design Note — Consumption-Surface Readiness (Sprint 6.2)

> **Status: proposal under review. Non-normative.** Everything above this heading is the
> scoring contract and is unchanged by this section. This note decides nothing, ships
> nothing, and clears no gate. Sprint 6.2's smallest slice is *"a `docs/SCORING.md`
> design note reviewed alone"* and this is that note; **Release Gate for Phase 6 stays
> open on all five criteria**, criterion 4 included, until a decision is reviewed and
> implemented in a separate `@scorer` boundary. No weight, threshold, cap, rollup, enum
> or engine behaviour moved in the commit that added this section.

### 1. The problem

A readiness verdict from this tool does not name the **consumption surface** it is about.
It says `READY` or `NOT_READY` for an object, and a reader supplies the missing noun from
whatever they came into the room thinking about.

That was tolerable while there was one path from an assessed object to an answer. There
are at least four, and they reach different object types. From a Microsoft Learn review
dated **2026-09-24** (product facts, not live-tenant observations; each is a documented
behaviour to be re-confirmed at implementation time, per `docs/KNOWN_LIMITATIONS.md` §8):

| Surface | Status | What it can reach | What it cannot |
|---|---|---|---|
| Fabric IQ plugin in Microsoft 365 Copilot **Cowork** | GA | Power BI reports and the semantic models behind them | paginated (RDL) reports, dashboards, share links, a semantic model named directly, and other Fabric items — **ontologies and data agents included** |
| Data answering in **Microsoft 365 Copilot Chat** | GA | Power BI content; a semantic model URL may be pasted | paginated reports, dashboards, top-level apps, report share links; data agents and ontologies *"can't answer questions in Copilot Chat **without an explicitly published Microsoft 365 agent**"* — **conditional, not absolute** |
| **In-Fabric agent surfaces** | varies | data agents and their sources | out of scope of the two above |
| **Ontology workload** | preview | ontology items | a different path again; see Sprint 6.3 |

The consequence is concrete and it is not hypothetical arithmetic. **An organisation can
score 100/100 on all fifteen Data Agent rules and get nothing in Cowork**, because Cowork
cannot reach a data agent at all. Every rule passed. Every finding green. The surface the
sponsor was actually asking about returns nothing. The verdict was not wrong about what it
measured; it was silent about what it was a verdict *for*, and silence in a steering
committee reads as coverage.

Note also that the two GA surfaces disagree with each other — Cowork's exclusion of data
agents is unqualified, Copilot Chat's is conditional on a published Microsoft 365 agent.
A single reachability statement phrased for "Microsoft 365 Copilot" would be wrong for one
of them. Per-surface is not an aesthetic preference; it is the minimum granularity at
which the sentence can be true.

This is the same category of error the **Non-Negotiable Contract** already forbids when it
keeps eligibility, score and confidence as three results that never substitute for one
another. Collapsing four reachability paths into one answer is collapsing four questions
into one number by a different route.

### 2. The binding constraint, and its inverse

Sprint 6.2 states the constraint directly:

> **The binding constraint: this must not become a single merged number.** Averaging
> per-surface readiness into one figure would recreate the exact defect it exists to fix,
> and adding a fourth headline result carries its own cost in comprehensibility.

The inverse failure is equally real and is the one a scoring engine drifts into when it
takes the first warning too literally. **Proliferating per-surface scores until nobody can
state whether the estate is ready is not honesty; it is abdication.** Four scores, four
eligibility flags and four confidences per object is twelve numbers where three were
already one too many for most readers, and an output nobody can summarise is an output
nobody acts on. "We refused to answer, in detail" is not a better failure than "we
answered the wrong question".

The design target is therefore narrow: **one readiness verdict per object, qualified by a
reachability statement that names its surface** — not four verdicts, and not one verdict
with a surface averaged into it.

### 3. The engine constraint — why reachability cannot simply be another rule today

This is the crux, and it is a fact about `ScoringEngine.score_object` as written, not an
opinion about design. A rule outcome has exactly three fates:

| Outcome | Score | Coverage | Finding emitted |
|---|---|---|---|
| `PASSED` / `FAILED` / `PARTIAL` | counts (`counts_towards_score`) | counts | yes |
| `NOT_EVALUATED` | no | **adds to `applicable_weight`, lowering coverage** | yes |
| `NOT_APPLICABLE` | no | skipped entirely — `continue` runs *before* `applicable_weight` | yes |

There is no fourth fate. Now read Sprint 6.1's validation criterion:

> a fixture with a paginated report and a dashboard produces a reachability finding
> **without altering either object's existing quality score**

and its non-goal:

> does not lower any existing report or model score because an object is unreachable —
> **reachability is a separate statement, not a quality deduction**

**That is not satisfiable with today's engine.** Work through the three fates:

- An honest `FAILED` on "unreachable by Cowork" **moves the score** — it enters
  `scored[dimension]`, drags the dimension mean down, and at `MAJOR` or `BLOCKING`
  severity applies a cap. Quality deduction, explicitly forbidden.
- `NOT_EVALUATED` does not move the score but **lowers coverage on every object the rule
  applies to**. If the rule is added and its evidence is unreadable, coverage falls
  estate-wide, and objects sitting just above the 50% floor drop to `NOT_EVALUATED`
  status. The score did not move; the published verdict did. It is also a lie about the
  facts: we know perfectly well that a paginated report is unreachable by Cowork. That is
  not a blind spot, it is a documented product behaviour.
- `NOT_APPLICABLE` is the only genuinely zero-impact outcome — and it means *out of scope,
  not unknown*. A paginated report is not out of scope. It is in scope and unreachable,
  which is precisely the finding we want to publish. Using `NOT_APPLICABLE` to dodge the
  score impact would bend the engine's vocabulary to evade a constraint. This project
  refuses that shortcut everywhere else — see the `FAILED` vs `NOT_EVALUATED` backbone
  above — and it should refuse it here.

**Roadmap finding, recorded for routing and not corrected here.** Sprint 6.1 item 7 says
the reachability rules *"may not be bundled with the Sprint 6.2 verdict change"*. The
dependency runs the other way: type-reachability rules **depend on** the 6.2 decision,
because until 6.2 decides where a reachability statement lives, there is no outcome a
reachability rule can honestly return. Sprint 6.1's own item 4 already hints at the same
thing — it hands `@semantic` "reachability by type" as a rule family — while item 5 asks
that family for a behaviour the rule vocabulary cannot produce. The tenant-setting and
endorsement families of 6.1 are unaffected and can proceed: those are ordinary,
score-bearing quality rules about observable configuration. Only the **type-reachability**
family is blocked. `docs/ROADMAP.md` is not edited by this note; the correction is routed
separately.

### 4. Candidate designs

Five shapes were considered. For each: what it does to `Scorecard`, to the Gold marts, to
the Power BI model, to the HTML and console reports, and to ruleset versioning and trend
comparability.

#### A — Reachability as a scoring `Dimension`

Add `Dimension.REACHABILITY` and give it weight in `DIMENSION_WEIGHTS` for reports,
semantic models and data agents.

- **`Scorecard`:** no new field; `dimension_scores` gains a key.
- **Marts / Power BI:** `dimension_scores_json` gains a key in `MartObjectReadiness` and
  friends — cheap, it is already a JSON blob.
- **Reports:** free; the dimension table renders it.
- **Versioning and trends:** expensive and estate-wide. Every object type's weights must
  be re-normalised to sum to 1.0, so **every existing weight moves**, so every historical
  score is incomparable. `_classify_delta` returns `RULESET_CHANGED` first, so the whole
  first cross-boundary comparison yields no quality signal at all.
- **Verdict: reject.** It *is* a quality deduction by construction — that is what a
  dimension is — and it violates the 6.1 non-goal directly. It also asserts something
  false: that an unreachable paginated report is a worse report. It is a perfectly good
  report on a surface that cannot see it. Worse, the deduction is un-actionable: the
  object owner cannot fix Cowork's item-type support.

#### B — Reachability as scorecard metadata, orthogonal to the score

A new field on `Scorecard`, populated from the inventory and from observed tenant
settings, mapping **surface → reachability state** over a four-state vocabulary:
`reachable` / `not_reachable` / `conditional` (with the condition named, e.g. *"requires
an explicitly published Microsoft 365 agent"*) / `not_evaluated`. The score, eligibility,
confidence and coverage maths are untouched.

- **`Scorecard`:** one additive optional field with a default, plus its `to_dict` /
  `from_dict` handling. `from_dict` defaulting to empty means **old baselines still
  load**, reading as "this run did not assess surfaces" — which is true of every run so
  far.
- **Marts:** either a JSON blob column (`surface_reachability_json`, following the
  `dimension_scores_json` / `notes_json` precedent) or a new long-format
  `MartSurfaceReachability` table keyed `(run_id, object_id, surface)`. `GOLD_SCHEMAS`
  already guarantees every table exists with an explicit typed schema even at zero rows,
  so adding a table is a known, tested operation.
- **Power BI:** a blob column costs one column and no measure; a long table costs a table,
  a relationship and a small measure set. The long shape is what a slicer wants.
- **Reports:** an HTML section and console lines; nothing existing changes shape.
- **Versioning and trends:** `compare_runs` reads only object identity, `score`,
  `coverage`, `confidence` and `ruleset_version`. An additive field it never touches does
  not itself break comparison. It must still carry a version increment — see §7 — but the
  comparison remains meaningful because the meaning of `score` is unchanged.
- **Verdict: viable, and the cheapest honest shape.** Its weakness is in §5.

#### C — Per-surface eligibility flags

Generalise `eligible` into `eligible_for: {surface: bool}`.

- **Verdict: reject.** Two objections, either sufficient. First, `eligible` means *clears
  every blocking rule* — a statement about the object's own quality. An object can be
  fully eligible and entirely unreachable; folding both into one word merges two
  independent facts under a name that already has a meaning, which is exactly the
  contract violation this note exists to prevent. Second, a boolean cannot express
  Copilot Chat's *conditional* answer or an unread tenant setting, and any encoding that
  forces `conditional` and `not_evaluated` into `false` manufactures a negative verdict
  out of a condition and out of ignorance respectively. There is also a mechanical hazard:
  `eligible` is consumed by rollups and by `MartRunSummary.eligible_object_count`, so
  changing its shape changes counts that appear on the front page.

#### D — A fourth published result alongside score, eligibility and confidence

- **Verdict: reject as a scalar; partially adopt as a layout.** Reachability is not a
  scalar per object, it is a vector over surfaces. Any scalar summary — "reachable by 2 of
  4 surfaces" — is precisely the merged number the roadmap forbids, arriving through the
  side door. The roadmap's comprehensibility objection also holds: confidence is already
  the result readers drop first, and a fourth peer would be dropped faster. What *is*
  worth taking from this option is the **placement**: whatever shape wins must appear
  adjacent to the headline, not three screens below it.

#### E — A new non-scoring `RuleStatus` that emits a finding without scoring

Add a fifth `RuleStatus` — `OBSERVED` / `INFORMATIONAL` — excluded from both
`counts_towards_score` and `applicable_weight`.

- **`Scorecard`:** none directly; the finding rides existing plumbing with its evidence,
  remediation text, docs link and owner role.
- **Marts / Power BI / reports:** a new badge and status string everywhere `RuleStatus` is
  rendered or counted.
- **Versioning and trends:** coverage denominators are unchanged if the status is excluded
  from `applicable_weight`, so trends survive. But **every** `RuleStatus` consumer must be
  audited: `counts_towards_score`, `score_object`, `_confidence`, `build_backlog`'s
  `wanted` set, calibration's `insufficient_evidence` handling and blinding, the preceptor
  checks, `not_evaluated_rules_json`, the console and HTML badges, and `RULES.md`
  generation.
- **Verdict: reject in this form, adopt a variant.** A fifth status excluded from scoring
  is a standing invitation to reclassify an inconvenient failure as "informational", and
  the engine could not tell the difference — the choice would sit in each check function,
  at runtime, invisible in review. The **variant worth keeping (E′)** moves the decision
  from the outcome to the rule: a rule declared **non-scoring at registration** (a flag on
  `Rule`, visible in `docs/RULES.md`, fixed at import time). Then non-scoring-ness is a
  reviewable property of the catalogue rather than a runtime choice, and the abuse
  requires a visible catalogue change.

### 5. Recommendation

**Adopt B.** Reachability is published as a per-surface, four-state block on the
scorecard, orthogonal to score, eligibility, confidence and coverage, and it is derived —
not scored. The score keeps its current meaning exactly.

Three reasons, in order of weight:

1. **It is the only option that makes the true statement.** "This report scores 88 for
   quality; Cowork can reach it; Copilot Chat can reach it; the ontology workload is not
   assessed" is four facts, each independently checkable. Every rejected option either
   deducts quality for a property the object owner cannot change, or merges facts that
   contradict each other across surfaces.
2. **Most of it needs no rule at all.** Type reachability is a lookup from a documented
   surface-capability table — *Cowork does not ground on paginated reports* is a product
   fact with a source and a verification date, exactly like the limits in
   `docs/KNOWN_LIMITATIONS.md` §8 — combined with observed tenant settings, which already
   have honest rules. Because it is not a rule outcome, **the §3 trilemma does not bind
   it**, and that resolves Sprint 6.1's unsatisfiable criterion without any vocabulary
   bending. E′ remains available later if a reachability property turns out to need
   per-object evidence, and it is separable from this decision.
3. **It is the only shape that leaves existing baselines readable.** An additive field
   with a default keeps every committed run loadable and keeps `compare_runs` meaningful,
   because the meaning of `score` never changes.

**The strongest counter-argument, stated plainly: the precedent I am leaning on does not
say what I want it to say.** `eligible` is offered as proof that an orthogonal, non-score
field works. But `eligible` works *because it is load-bearing*: the engine itself revokes
it, caps the score at 39, forces `NOT_READY` and propagates a cap to the parent. It cannot
be ignored by a downstream consumer because it has already changed the number they are
looking at. A reachability block has no such teeth. It is passive metadata, and passive
metadata is dropped — by a mart query that selects the columns it knows, by an HTML
section below the fold, by a slide that quotes the headline. The failure mode the whole
sprint exists to prevent — a green verdict that does not name its surface — **survives
option B intact** unless something else enforces the naming.

I do not think that sinks the recommendation, but the mitigation must be part of the
decision rather than deferred, and the mitigation is weaker than a cap: the **run-level
surface statement** — *"this run assessed reachability for surfaces X and Y; it did not
assess Z"* — must be rendered adjacent to every headline in console, HTML and
`MartRunSummary`, and the preceptor must fail a run that publishes a headline without it.
An enforced sentence is not as strong as an enforced number. Anyone who thinks that gap is
unacceptable should argue for E′ with a `BLOCKING` reachability rule on the surfaces the
customer has actually declared they are buying — which is a coherent position, and is
where I would go if the mitigation proves unenforceable in review.

### 6. What would falsify the recommendation

Named in advance, so the decision can be reopened on evidence rather than on preference:

1. **Reachability turns out to be remediable per object.** If endorsing a model measurably
   changes whether Cowork finds it, then discoverability is a quality property with a
   remediation and an owner, and it belongs in the backlog and plausibly in the score.
   That would split the family: endorsement becomes ordinary scored rules (as Sprint 6.1
   already plans), while *type* reachability stays a statement. Option A would still be
   wrong for item type; it would become arguable for discoverability.
2. **Operators need to triage by reachability at scale.** If the real question is "show me
   the 400 objects unreachable from Cowork, ranked by usage", a JSON blob is the wrong
   shape and a first-class long mart table with its own slicer is required. This does not
   change the decision, it changes the storage shape inside it — but it should be settled
   before implementation, not after the mart ships.
3. **The surfaces converge.** If Microsoft unifies Cowork and Copilot Chat reachability,
   the vector collapses to a scalar and a single flag suffices; the per-surface structure
   becomes overhead.
4. **The surfaces multiply faster than they are maintained.** In-Fabric agents, Copilot
   Studio agents, Foundry IQ agents and custom agents over the ontology MCP server are
   already five more paths. If the catalogue cannot be kept current with sourced,
   dated facts, a fixed key set becomes stale documentation published as data — at which
   point reporting *fewer* surfaces honestly beats reporting all of them badly.
5. **A reviewer demonstrates the run-level statement cannot be enforced.** If the headline
   can still be quoted without its surface qualifier after the mitigation is in place, the
   passive-metadata objection wins and E′ with real severity becomes the better answer.

### 7. What is explicitly not decided, and what must happen first

**Not decided by this note:**

- The field name, the storage shape (blob column vs long mart table), and the exact
  surface identifiers.
- Whether reachability appears in the remediation backlog. `build_backlog` currently
  selects `FAILED` and optionally `PARTIAL`; an unreachable item type has no remediation
  its owner can perform, and a backlog item nobody can close is noise.
- Whether rollups say anything about reachability. Aggregating child reachability into a
  parent is a merge, and merges are what this note is about. The default is **silence at
  parent level** until someone argues otherwise.
- Whether the ontology workload appears as a surface before Sprint 6.3 gives it an object
  type.
- Whether `conditional` renders differently from `reachable` in the headline. It differs
  in fact; whether the difference survives the summary is a presentation decision for
  `@preceptor` and `@readme`.

**Required before any implementation:**

1. **Sprint 6.1's availability record lands first.** The tenant-setting and endorsement
   inputs must exist in `docs/API_REALITY_MATRIX.md`, with the identity that obtained
   them, before the verdict tries to express them. A surface state derived from an
   unread setting is `not_evaluated`, never a vendor default.
2. **Regression tests in `tests/test_scoring.py`**, at minimum: a strong-on-Data-Agent,
   unreachable-from-Cowork fixture produces no output readable as "ready for Cowork"; a
   paginated report and a dashboard carry `not_reachable` for Cowork **with `score`,
   `raw_score`, `status`, `eligible`, `confidence` and `coverage` byte-identical to the
   same fixture without the feature**; an unread tenant setting yields `not_evaluated` for
   the affected surface and does **not** alter coverage; the 39 cap, the 59 cap, the 50%
   floor and the renormalisation test keep passing unchanged; and a round trip through
   `to_dict`/`from_dict` preserves the block.
3. **Ruleset-version handling.** Today `ruleset_version` is the only comparability key,
   and it is a *rule catalogue* version being asked to guard a *payload shape*. Shipping a
   scorecard shape change without incrementing it would let two structurally different
   runs look comparable; incrementing it makes `_classify_delta` return `RULESET_CHANGED`
   for every object in the first cross-boundary comparison, costing one run of trend
   signal. The second cost is the correct one to pay, and the note records that it is a
   cost and not free. Whether a payload-schema version distinct from the ruleset version
   is warranted is a separate question worth asking at that point.
4. **Migration for existing baselines.** `Scorecard.from_dict` must default the new field
   so every committed run and every stored artifact still loads, reading as "surfaces not
   assessed" — which is accurate. New mart columns follow the `GOLD_SCHEMAS` discipline:
   explicit type, always present, zero rows permitted. `compare_runs` must not classify
   "the field appeared" as a change in the estate.
5. **A sourced, dated surface-capability table**, owned by `@readme` in
   `docs/KNOWN_LIMITATIONS.md` §8 style. Every encoded Cowork or Copilot Chat limit
   carries its public source and exact verification date so a product change is
   detectable rather than silently wrong. This note's §1 table is a summary of that
   review, not a substitute for it, and must not be cited as the encoded limit.

**Commit boundaries, per Sprint 6.2 item 7.** This note is one boundary, reviewed alone.
Any accepted model or maths change is a separate `@scorer` boundary with a ruleset
increment, migration handling and regression tests. Mart, Power BI and report changes
follow in a third, never in the same commit as the maths.
