# Architecture

## Pipeline

```
┌──────────────┐   read-only    ┌───────────┐
│ Fabric /     │ ─────────────→ │ Collector │ ──→ Bronze: raw payloads, hashed
│ Power BI API │                └───────────┘        endpoint, timestamp, status
└──────────────┘                      │
                                      ▼
                               Silver: normalized inventory
                               tenant + workspaces + semantic_models
                               + reports + data_agents
                                      │
                                      ▼
                              ┌──────────────┐
                              │ Rule Registry│  65 rules, 5 object types
                              └──────────────┘
                                      │
                                      ▼
                              ┌──────────────┐
                              │ScoringEngine │  caps, renormalization, rollups
                              └──────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
             Remediation        Preceptor          Lakehouse
             backlog            review             Gold marts
                                                   + console / HTML
                                                        │
                                                        ▼
                                          Direct Lake semantic model
                                          (IsFabricReadyForIQ.SemanticModel)
                                                        │
                                                        ▼
                                          Power BI report
                                          (IsFabricReadyForIQ.Report)
```

The last two stages are **Fabric-only** — they read the same Gold Delta tables a
scheduled notebook run writes, so a local NDJSON run has nothing to render there. See
[`fabric/README.md`](../fabric/README.md) for the deployed item list and
[`docs/INSTALL.md`](INSTALL.md) for how the whole surface (Lakehouse, notebook, pipeline,
semantic model, report) is deployed by a single installer notebook that clones
[`cyphou/FIQA`](https://github.com/cyphou/FIQA) into the target workspace.

Every deploy also reconciles the workspace's default Spark runtime toward
`DEFAULT_SPARK_RUNTIME_VERSION` (Spark 4.1 / Delta Lake 4.2 as of Runtime 2.0), via an
idempotent `GET`-then-`PATCH` against `workspaces/{id}/spark/settings` — the notebook has
no runtime-specific code, so it always benefits from the newest generally-available
runtime. `fabric/deploy.py --skip-spark-runtime-upgrade` opts out. See
[`fabric/README.md`](../fabric/README.md#-spark-runtime-auto-upgrade) for the exact flags
and output.

## Modules

| Module | Responsibility | Owner |
|--------|---------------|-------|
| `assess.py` | CLI, run lifecycle, exit codes | `@orchestrator` |
| `fabric_iq/errors.py` | Domain error hierarchy | `@orchestrator` |
| `fabric_iq/collectors/` | Evidence acquisition and normalization | `@collector` |
| `fabric_iq/rules/base.py` | Rule primitives and registry | `@scorer` |
| `fabric_iq/rules/*_rules.py` | The catalogue | `@tenant`, `@semantic`, `@dataagent` |
| `fabric_iq/models.py` | Shared data model | `@scorer` |
| `fabric_iq/scoring.py` | Scoring engine and rollups | `@scorer` |
| `fabric_iq/preceptor.py` | Preceptorship review loop | `@preceptor` |
| `fabric_iq/remediation.py` | Prioritised backlog | `@remediation` |
| `fabric_iq/lakehouse.py` | Medallion persistence | `@lakehouse` |
| `fabric_iq/reporting.py` | Console and HTML output | `@lakehouse` |
| `fabric_iq/deployment.py` | Deploy/update the Fabric item surface (Lakehouse, notebook, pipeline, semantic model, report) and the workspace's default Spark runtime | `@lakehouse` |
| `fabric/items/` | Deployed Fabric artifacts: Lakehouse, assessment notebook, orchestration pipeline, Direct Lake semantic model, Power BI report, installer notebook | `@lakehouse` |

## Data Model

```
AssessmentRun
 ├── run_id, tenant_id, ruleset_version, collector_mode, timestamps
 └── Scorecard[]                     one per object
      ├── object_id / type / parent_id
      ├── score, raw_score, status, eligible, confidence, coverage
      ├── dimension_scores{}
      └── Finding[]                  one per rule evaluated — full audit trail
           ├── rule_id, title, dimension, severity, effort, owner_role
           ├── remediation, docs
           └── RuleOutcome
                ├── status, score, detail, observed{}
                └── Evidence[]       source, reference, detail
```

`Scorecard.findings` holds **every** rule outcome, not only the failures. A reviewer
asking "did you check RLS on this model?" needs an answer even when the answer is
"yes, it passed" or "we could not". `failed_findings` and `blocking_findings` filter
that trail for reporting.

## Collection Layers

### Bronze — proof

Immutable `BronzeRecord` per upstream call: endpoint, timestamp, status code, duration,
correlation id, identity, content hash, payload. This is what makes a finding
reproducible six weeks later, when the tenant has changed and someone disputes the
verdict.

### Silver — the contract

`CollectionResult.validate()` guarantees five sections exist with the correct types.
Downstream code may trust that and **nothing more** — in particular, it may not assume
any field inside an object is present. Absent fields are the normal case, handled by
`require()` producing `NOT_EVALUATED`.

### Gold — the marts

| Mart | Grain |
|------|-------|
| `MartRunSummary` | run |
| `MartTenantReadiness` | tenant × run |
| `MartWorkspaceReadiness` | workspace × run |
| `MartObjectReadiness` | model / report / agent × run |
| `MartBlockingFindings` | blocking finding × run |
| `MartRemediationBacklog` | backlog item × run |
| `MartCoverageAndFreshness` | object × run |

Every row carries `run_id`. `MartRunSummary` is intentionally one row per run and gives
Copilot, Fabric IQ and Data Agents a simple entry point for the current assessment:
tenant id, ruleset version, run timestamps, object counts, blocking findings, backlog
size and average object score/confidence/coverage.

NDJSON is the durable development and medallion format: every run is written under its
own `run_id`, and re-running the same `run_id` is idempotent. Delta is the Fabric
DirectLake target. By default the deployed notebook overwrites the Delta marts with the
latest snapshot (`delta_publish_mode = "overwrite"`) so the report remains intelligible
and does not duplicate objects across historical runs. Set `delta_publish_mode =
"append"` only for deliberate trend experiments; the medallion JSONL files remain the
authoritative run history either way.

## Error Handling

All failures raise an `AssessmentError` subclass: `CollectionError`, `ThrottlingError`,
`NormalizationError`, `RuleError`, `ScoringError`, `PersistenceError`,
`ConfigurationError`, `ReviewError`.

`Rule.evaluate()` degrades `KeyError`, `TypeError`, `ValueError` and `AttributeError`
into `NOT_EVALUATED`: a rule written against a field that turns out to be absent must
reduce confidence, not crash a four-hour scan. The tuple is deliberately narrow — a
genuine defect such as a `ZeroDivisionError` still surfaces rather than hiding as a
coverage gap.

## Design Constraints

- **Standard library only** for the core engine — it must run inside a Fabric notebook
  with no package installation.
- **Read-only** collection. No write scope, no state change, no flag that enables one.
- **Deterministic** scoring: the same inventory produces the same scores. No sampling,
  no model calls, no randomness in the verdict.
