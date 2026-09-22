# Roadmap — IsFabricReadyForIQ

Owner: **@roadmap-planner**. This document is authoritative for scope and release gates.

## Purpose

Tell an organisation, with evidence, whether its Power BI / Fabric estate is ready for
Fabric IQ and agentic experiences — and exactly what to change, object by object.

## Principles That Constrain The Sequence

1. **Discovery order is the product.** Finding a capacity blocker in week 1 is worth more
   than a perfect semantic-model rule catalogue in month 4. Cheap, wide, blocking checks
   come before deep, narrow, quality checks.
2. **Never plan on an unconfirmed API.** Every phase that depends on a metadata surface
   opens with a proof of concept against a real tenant. A day of verification protects
   a month of design.
3. **Static readiness is a prediction; agent evaluation is a measurement.** They are
   sequenced separately and never conflated.
4. **The programme is a trend, not a snapshot.** Re-measurement is a phase, not a nicety.

## Status Summary

| Phase | Theme | Status |
|-------|-------|--------|
| 0 | Framing and contract | ✅ Done |
| 1 | Inventory and live collection | ✅ Done — all four sprints closed and field-validated |
| 2 | Static readiness scoring | 🟡 Engine done (65 rules), catalogue-hardening pass (Sprint 2.1) still open |
| 3 | Agentic readiness | 🟡 Rules done, evaluation harness missing |
| 4 | Industrialisation | 🟡 Scheduling, Delta persistence, semantic model/report and CI gate shipped; trend/regression detection (Sprint 4.3) open |
| 5 | Fabric IQ extension | ⏳ Continuous |

---

## Phase 0 — Framing and Contract (2 weeks) ✅

**Outcome.** A scoring contract that survives contact with a steering committee, and a
working end-to-end skeleton on synthetic fixtures.

**Delivered.**

- Three-result contract: eligibility, readiness score, confidence — never merged
- Severity caps: blocking → 39 and ineligible, major → 59, caps only lower
- `NOT_EVALUATED` as a first-class outcome, distinct from failure and from absence of scope
- Coverage floor: below 50% the object is not published with a score
- 65-rule catalogue across tenant, workspace, semantic model, report and Data Agent
- Medallion persistence, prioritised remediation backlog, preceptorship loop
- Multi-agent environment with enforced file ownership

**Exit gate.** ✅ `python assess.py --inventory examples/sample_tenant --review` produces a
scored run; `python -m unittest discover -s tests -t .` is green; ownership audit clean.

**Non-goals.** No live tenant. No automated remediation. No trend analysis.

---

## Phase 1 — Inventory and Live Collection (4–6 weeks) ✅

> **Status update.** `fabric_iq/collectors/fabric_api.py` (stdlib HTTP transport,
> Scanner `getInfo`, pagination, bounded 429 retry, Bronze evidence, checkpoint resume)
> and the `fabric/` Fabric-native deployment (Lakehouse + Notebook + DataPipeline) have
> both been **field-validated against a real tenant** — see
> `docs/KNOWN_LIMITATIONS.md` §1.1–§1.2 for the full record (tenant scorecard produced,
> 7 real workspaces rolled up, a correct blocking finding on a non-Copilot-eligible
> trial capacity, pipeline `fail_on_blocking` gate proven on two live runs). Sprint 1.1's
> availability table exists and is honest about gaps (roughly 8 of 17 `SEM-*` rules
> evaluate on live Scanner output; `throttled` is not returned by `/admin/capacities`).
> What remains open from this phase: nothing — all four Phase 1 sprints are closed.
> Sprint 1.2 (simulated 500-workspace quota-scale validation), Sprint 1.3 (incremental
> semantic-model deep-metadata path), and Sprint 1.4 (identity/scope/retention decision)
> are documented in `docs/KNOWN_LIMITATIONS.md` §1.3, `docs/IDENTITY_AND_RETENTION.md`,
> and validated by `tests/test_live_collection.py` / `tests/test_preceptor.py`.

**Outcome.** A real tenant can be scanned end to end, with resumable collection and an
auditable evidence trail.

### Sprint 1.1 — API reality proof of concept (3 days)

- **Anchor.** `FabricApiCollector` has a contract and normalization, no transport.
- **Hypothesis.** Every field the rule catalogue consumes is obtainable read-only.
- **Cheap check.** For one workspace, retrieve: tenant settings, capacity state, workspace
  inventory, semantic model metadata (tables, columns, measures, descriptions), AI data
  schema / Prep-for-AI configuration, AI instructions, verified answers, RLS roles,
  Data Agent definition and its data sources.
- **Expected outcome.** A field-by-field table: *available / partial / not exposed*.
- **Owner.** `@collector`, reviewed by `@security` for scope minimality.
- **Exit gate.** The table is committed to `docs/KNOWN_LIMITATIONS.md`. Every rule reading
  a field marked *not exposed* is reclassified as permanently `NOT_EVALUATED` with an
  explicit note, or deleted. **No rule silently keeps a field the API cannot provide.**

> This sprint can invalidate parts of Phase 2 and 3. That is its job, and it is why it
> runs first and costs three days rather than three weeks.

### Sprint 1.2 — Scanner transport with quota discipline (1.5 weeks) ✅

- Batched `getInfo` (100 workspaces/request, 16 concurrent), `modifiedSince` windows
  capped at 30 days, exponential backoff honouring `Retry-After`.
- Checkpointing: a scan interrupted at hour 3 resumes, it does not restart.
- Every call emits a `BronzeRecord`; every failure emits a `record_error`.
- **Validation.** Simulated 429 mid-scan resumes and completes; injected-transport tests.
- **Exit gate.** A 500-workspace simulated tenant completes within quota, and the run
  reports its own coverage honestly.
- **Delivered.** `FabricApiCollector._throttle_getinfo_quota` enforces
  `MAX_GETINFO_CALLS_PER_HOUR` proactively (rolling one-hour window, sleeps before the
  ceiling rather than reacting to a 429). `test_getinfo_quota_throttles_proactively_before_the_hourly_ceiling`,
  `test_throttled_mid_scan_resumes_to_completion_from_checkpoint`, and
  `test_large_tenant_scan_reports_honest_partial_coverage_on_batch_failure` in
  `tests/test_live_collection.py` cover, respectively: proactive throttling before the
  ceiling, checkpoint-resume after a mid-scan throttle, and a 500-workspace tenant with a
  permanently failed batch reporting `workspaces_total=500, workspaces_scanned=400` plus a
  recorded error rather than inventing the missing 100. `MAX_CONCURRENT_SCANS` and
  `modified_since_days` were deliberately kept sequential/unwired — see
  `docs/KNOWN_LIMITATIONS.md` §1.3 for the reasoning.

### Sprint 1.3 — Semantic model deep metadata (1.5 weeks) ✅

- Model metadata via the appropriate read surface, incremental where possible.
- Graceful degradation: an unreadable model is `NOT_EVALUATED` with `schema_retrieval_error`,
  never a zero, never a pass.
- **Exit gate.** A tenant with a mix of readable and unreadable models produces correct
  per-object coverage, and the preceptor scores *rule coverage* honestly.
- **Delivered.** Already covered before this closure pass: Sprint 1.1's live validation
  confirmed roughly 8 of 17 `SEM-*` rules evaluate on real Scanner output, and
  `tests/test_preceptor.py` already exercises a tenant with a mix of readable/unreadable
  models, asserting the preceptor reports rule coverage honestly rather than silently
  scoring the gaps as passes.

### Sprint 1.4 — Identity, scopes and retention (1 week) ✅

- Service principal with least-privilege read scopes, documented.
- Retention and residency decision for Bronze payloads, with optional field redaction.
- **Owner.** `@security`.
- **Exit gate.** A written scope and retention decision; no write scope anywhere; the
  privacy audit passes on a real run's artifacts.
- **Delivered.** [`docs/IDENTITY_AND_RETENTION.md`](./IDENTITY_AND_RETENTION.md): documents
  the six admin-read endpoints the collector ever calls, the corresponding
  `Tenant.Read.All` / `Workspace.Read.All` app-registration scopes, why `getInfo`'s `POST`
  is still read-only, the Bronze retention/redaction decision, and a manual privacy-audit
  checklist for a real run's artifacts. "No write scope anywhere" is enforced in code by
  `FabricHttpTransport._validate_request` / `READ_ONLY_SCANNER_POSTS`
  (`fabric_iq/collectors/fabric_api.py`) and asserted by
  `tests/test_live_collection.py::test_rejects_writes_and_non_scanner_post`.

**Phase exit gate.** One real tenant scanned end to end; coverage reported per object;
zero tenant writes; the preceptorship loop approves the run at ≥ 4★ or escalates with
named blind spots.

**Risks.** Prep-for-AI and Data Agent metadata may be partially or entirely unavailable
through public APIs. Mitigation: Sprint 1.1 decides this before anything is built on it.

---

## Phase 2 — Static Readiness Scoring (3–4 weeks) 🟡

**Outcome.** Scores that a data platform owner accepts as fair, and a backlog a delivery
lead can hand out on Monday.

### Sprint 2.1 — Catalogue hardening against reality (1.5 weeks)

- Reconcile all 65 rules (including the two INFO-severity Copilot-capacity advisories,
  TEN-011 and WKS-011, added after live testing showed capacity is a recommendation
  rather than a blocker — see `docs/KNOWN_LIMITATIONS.md` §8) against the Sprint 1.1
  availability table.
- Re-verify every encoded product limit and date it: 5 data sources, 25×25 result surface,
  200-character description budget, 10,000-character AI instructions, F2+/P1+ capacity.
- **Owners.** `@tenant`, `@semantic`, `@dataagent`; documentation by `@readme`.
- **Exit gate.** `python assess.py --list-rules` matches the documented catalogue; every
  limit carries a source and a verification date.

### Sprint 2.2 — Calibration on a real estate (1 week)

- **Anchor.** Weights are currently reasoned, not calibrated.
- **Cheap check.** Score 20–30 real objects; have two practitioners independently label
  them ready / not ready; measure agreement with the tool's verdict.
- **Expected outcome.** Systematic disagreements point at a weight or a threshold.
- **Exit gate.** Documented calibration with disagreements explained. Weights change only
  with a recorded rationale and a regression test. **A weight is never tuned to make a
  specific tenant look better** — that is the one change `@scorer` must refuse.

### Sprint 2.3 — Backlog usability (1 week)

- Owner-role grouping, effort roll-up per role, top-N views, CSV for a delivery tool.
- **Exit gate.** A delivery lead can, from one CSV, assign ten items with an owner, an
  action and an estimate — without reading the scoring documentation.

**Phase exit gate.** Practitioner agreement documented; backlog actionable without
interpretation; scoring contract unchanged (three results, never merged).

---

## Phase 3 — Agentic Readiness (4 weeks) 🟡

**Outcome.** A Data Agent verdict backed by measured behaviour, not by configuration
inspection alone.

### Sprint 3.1 — Evaluation corpus format (1 week)

- Schema: question, expected answer or expected DAX intent, criticality flag, persona,
  paraphrase variants, out-of-scope negatives.
- **Owner.** `@dataagent`.
- **Exit gate.** A documented format plus a synthetic reference corpus in `examples/`.
  **The tool measures a corpus; it does not author one.** A corpus without business
  ownership measures nothing worth knowing.

### Sprint 3.2 — Evaluation harness (2 weeks)

- Execute a corpus against an agent, per persona, capture answer, generated query,
  latency, refusal behaviour.
- Compute: overall accuracy (≥ 85%), critical accuracy (≥ 95%), refusal correctness,
  leakage (any incident blocking), latency p95.
- **Exit gate.** A run against a real agent produces reproducible metrics that feed
  AGT-006 … AGT-012 as evidence rather than as declared inputs.

### Sprint 3.3 — Persona isolation (1 week)

- Minimum two personas; cross-persona leak detection is blocking with no cap relief.
- **Owner.** `@security` co-reviews; transcripts are customer data with a retention decision.
- **Exit gate.** A deliberately misconfigured RLS agent is caught by the harness.

**Phase exit gate.** An agent verdict distinguishes *structurally eligible* from
*behaviourally correct*, and never reports the second without evidence.

**Non-goals.** No automatic prompt or instruction rewriting. No agent authoring.

---

## Phase 4 — Industrialisation (4–6 weeks) 🟡

**Outcome.** Readiness becomes a recurring, trended programme rather than a one-off audit.

### Sprint 4.1 — Scheduled runs and Delta persistence (2 weeks) ✅ Delivered

- Fabric notebook or pipeline execution; Gold marts written as Delta with the same schema
  as the local NDJSON output, so a local run and a scheduled run stay comparable.
- **Delivered as:** [`Fabric_IQ_Readiness_Assessment.Notebook`](../fabric/items/Fabric_IQ_Readiness_Assessment.Notebook/notebook-content.py)
  orchestrated by [`Fabric_IQ_Readiness_Orchestration.DataPipeline`](../fabric/items/Fabric_IQ_Readiness_Orchestration.DataPipeline),
  writing `Mart*` Delta tables into [`FabricIQReadiness.Lakehouse`](../fabric/items/FabricIQReadiness.Lakehouse)
  — see [`fabric/README.md`](../fabric/README.md).
- Deploy also reconciles the workspace's default Spark runtime toward the newest
  generally-available version (Runtime 2.0 = Spark 4.1 / Delta Lake 4.2) via an
  idempotent `GET`-then-`PATCH`, so scheduled runs pick up engine improvements without a
  manual trip through Workspace settings. `--skip-spark-runtime-upgrade` opts out.
- **Exit gate.** Two consecutive scheduled runs are queryable side by side by `run_id`.

### Sprint 4.2 — Readiness semantic model and report (1.5 weeks) ✅ Delivered

- Direct Lake model over the Gold marts; report pages: tenant posture, workspace ranking,
  blocking findings, backlog by owner, coverage and freshness.
- The readiness model must itself pass this tool's SEM rules. Shipping an AI-readiness
  assessor whose own model is not AI-ready is not a joke we can afford twice.
- **Delivered as:** [`IsFabricReadyForIQ.SemanticModel`](../fabric/items/IsFabricReadyForIQ.SemanticModel)
  (Direct Lake over the Lakehouse `Mart*` tables) and [`IsFabricReadyForIQ.Report`](../fabric/items/IsFabricReadyForIQ.Report)
  (FCA/FUAM-styled pages), both deployed by the installer notebook — see
  [`docs/INSTALL.md`](INSTALL.md).
- **Exit gate.** The readiness model scores ≥ 85 under its own rules. *Not yet re-verified
  against the shipped model* — re-run this tool against the deployed semantic model itself
  before closing this gate formally.

### Sprint 4.3 — Trend and regression detection (1.5 weeks) ⏳ Open

- Score deltas per object between runs, new blocking findings, remediation burn-down.
- Distinguish a genuine regression from a coverage change: **an object that dropped because
  we could no longer read it is a collection incident, not a quality regression.**
- **Exit gate.** A seeded regression and a seeded coverage loss are reported differently.

### Sprint 4.4 — CI gate (1 week) ✅ Delivered

- `--fail-on-blocking` (exit 2) and `--fail-on-review` (exit 3) wired into a deployment gate.
- **Delivered as:** CLI flags in [`assess.py`](../assess.py), exercised by
  [`tests/test_pipeline.py`](../tests/test_pipeline.py) and wired into
  [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
- **Exit gate.** A pipeline blocks on a blocking finding and reports the reason without
  log parsing.

**Phase exit gate.** A monthly run produces a trend, a burn-down, and a gate — unattended.
Scheduling, persistence, the semantic model/report and the CI gate are shipped; only
Sprint 4.3 (trend/regression detection) remains to close this phase.

---

## Phase 5 — Fabric IQ Extension (continuous) ⏳

**Outcome.** The catalogue tracks the platform instead of ageing against it.

- **Ruleset versioning.** `RULESET_VERSION` pins what was believed true at scoring time.
  A score is only comparable across runs when the ruleset version matches; when it does
  not, the trend view must say so rather than plotting the two together.
- **Quarterly limit review.** Product limits change. `@readme` gates the release on
  re-verification with dates.
- **Ontology and DTB readiness.** Extend to Fabric IQ ontology objects as their metadata
  surface stabilises. Gate: no rule ships against a preview surface without a
  `preview_dependencies` flag on the object.
- **Retirement watch.** Power BI Q&A is announced for retirement in December 2026 — add
  no new dependency, and flag existing ones as technical debt.

**Exit gate (per quarter).** Every encoded limit re-verified and dated; no rule depends on
a retired surface; the trend view refuses to plot across incompatible ruleset versions.

---

## Cross-Cutting Gates

Applied to every phase, without exception:

| Gate | Check |
|------|-------|
| Read-only | No collector holds or uses a write scope |
| Evidence | Every finding names a reproducible source |
| Three results | Score, eligibility and confidence remain separate |
| Caps | Blocking → 39 and ineligible; major → 59; caps only lower |
| Coverage | Below 50% publishes `NOT_EVALUATED`, not a score |
| Ownership | `python scripts/check_agent_ownership.py` is clean |
| Tests | `python -m unittest discover -s tests -t .` is green |
| Privacy | Pre-push audit passes; fixtures are synthetic |
| Review | The preceptorship loop approves at ≥ 4★ or escalates explicitly |

## What This Project Will Not Do

- **Modify a tenant.** No enablement, no description generation in place, no auto-fix.
  The moment this tool writes, it stops being trusted with read access to production.
- **Replace human judgement on business criticality.** It can measure a model; it cannot
  know which model matters.
- **Author an evaluation corpus.** It measures the corpus the business owns.
- **Guarantee agent quality from static metadata.** A perfect static score is a prediction.
  Only Phase 3 measurement turns it into a claim.
