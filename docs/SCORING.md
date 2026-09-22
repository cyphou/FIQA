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

## Ruleset Versioning

Every scorecard records `ruleset_version`. Scores are comparable across runs **only when
the ruleset version matches**. When product limits change and the catalogue changes with
them, a score shift may reflect the new ruleset rather than a real change in the estate.
Trend views must refuse to plot across incompatible versions rather than silently mixing
them and reporting an improvement nobody made.
