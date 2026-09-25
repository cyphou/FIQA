# FIQA Self-Assessment Gate

This document closes the Phase 4 formal self-assessment gate for the
`IsFabricReadyForIQ` readiness semantic model and report.

The gate is intentionally executable rather than only descriptive:

```bash
python -m unittest tests.test_self_assessment
```

The test loads the synthetic fixture in
`examples/fiqa_self_assessment/`, scores it with the same engine as any other tenant
inventory, and fails unless both the FIQA semantic model and the FIQA report are:

- eligible,
- `READY`,
- scored at least 85,
- at least 90% confident,
- at least 90% covered,
- free of blocking findings.

## Gate Result

| Object | Status | Eligible | Score | Confidence | Coverage | Blocking findings |
|--------|--------|----------|------:|-----------:|---------:|------------------:|
| `IsFabricReadyForIQ` semantic model | `READY` | yes | 100 | 91.2% | 92.5% | 0 |
| `IsFabricReadyForIQ` report | `READY` | yes | 100 | 100.0% | 100.0% | 0 |

The deployed model was also validated live before this gate was documented:

- `MartRunSummary` returned the current run `run_20260923T072239Z`.
- `MartRemediationBurnDown` was queryable through DirectLake.
- The remediation burn-down mart contained 44 rows, all `open`, with zero priority and
  effort delta from the comparable baseline.

## Evidence Boundaries

The committed fixture is synthetic. It captures the required readiness shape of the FIQA
semantic model/report without storing tenant identifiers, tokens, credentials, user
data, workspace IDs, or report URLs.

Live Fabric identifiers and validation run IDs are operational deployment evidence, not
fixture data. They should stay in deployment logs or release notes rather than in the
offline inventory fixture.

### Fixture fields are declarations, not observations

Every field in the fixture states what FIQA **must** look like to be called ready. None
of it is a reading taken from a deployed artefact. Most fields are structural and can be
checked against this repository's own contents — a star schema, measure descriptions,
naming. A few cannot, and those carry a higher duty of care, because a reader can mistake
a declaration for a measurement.

`endorsement` / `endorsement_certified_by` are of the second kind. They were added to both
objects in the same change that added the rules reading them (`SEM-018`, `REP-011`), and
they are a **declared requirement**: FIQA's readiness shape includes being endorsed, so
that Microsoft 365 Copilot discovery has a ranking signal for it. They are *not* evidence
that the deployed FIQA model or report is currently endorsed in any tenant. Unlike the
structural fields, `endorsement` is populated from a live Scanner scan
(`FabricApiCollector._endorsement`), so this declaration is falsifiable against a real
deployment and must never be cited as though that check had been run.

`"Promoted"` is deliberate rather than `"Certified"`. Certification asserts a
tenant-authorised certifier, which this project cannot evidence; promotion is
self-attestation by the content author, which it can. The weaker claim also costs nothing
— both values score identically — so there was no incentive pulling toward the stronger
one.

Adding a field so a gate keeps passing is a pattern that deserves suspicion, so the
specific objection was tested rather than waved through. It does not hold here: with
`endorsement` declared as `""` — the honest negative, "this item carries no endorsement" —
both objects still pass every gate condition (model 98.4, report 96.0; confidence and
coverage unchanged). What restores confidence is the fixture *answering* a question the
catalogue now asks, not the answer being flattering. A fixture silent on a shipped rule is
an incomplete fixture, and its low confidence reports that incompleteness rather than
anything about FIQA.

The standing limit: this reasoning licenses declaring a requirement, never declaring a
result. Any fixture field that a collector can populate from a live scan must be
justifiable as something FIQA ought to be, and must not be read back as proof that it is.
