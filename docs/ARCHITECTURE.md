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
                              │ Rule Registry│  61 rules, 5 object types
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
```

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
| `MartTenantReadiness` | tenant × run |
| `MartWorkspaceReadiness` | workspace × run |
| `MartObjectReadiness` | model / report / agent × run |
| `MartBlockingFindings` | blocking finding × run |
| `MartRemediationBacklog` | backlog item × run |
| `MartCoverageAndFreshness` | object × run |

Every row carries `run_id`. Writes append; a re-run of the same `run_id` is idempotent.
The value of the third assessment is that it can be compared to the first, so history is
never overwritten.

NDJSON is the development format; Delta is the Fabric target. The schema is identical so
that a local run and a scheduled notebook run remain comparable.

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
