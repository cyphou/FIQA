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
