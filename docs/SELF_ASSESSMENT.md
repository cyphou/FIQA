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
| `IsFabricReadyForIQ` semantic model | `READY` | yes | 100 | 90.8% | 92.3% | 0 |
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
