# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Live-tenant validation, a growing rule catalogue, and a Fabric-native delivery surface
(semantic model, report, installer notebook) on top of the 0.1.0 engine.

### Added

**Rule catalogue** — grown from 61 to **65 rules**, ruleset `2026.09.1`
- `TEN-011` (tenant) and `WKS-011` (workspace) — advisory, `Severity.INFO` recommendations
  to designate a capacity as a **Fabric Copilot capacity** for billing-attribution
  purposes only. Added, then removed after a live F2-capacity tenant test proved Data
  Agents and Copilot function without this designation, then reinstated as
  non-blocking advisories once the "billing attribution, not a functional gate" framing
  was confirmed. `WKS-011` is `not_applicable` once a workspace's capacity already meets
  the native-Copilot threshold (F64/P1-equivalent). See
  [`docs/KNOWN_LIMITATIONS.md` §8](./docs/KNOWN_LIMITATIONS.md#8-product-limits-age).
- Full history of tenant-level (`TEN-012`) and capacity-eligibility rule wording refined
  after the same live-tenant pass.

**Fabric deployment surface** (new, via an FCA/FUAM-style installer)
- [`fabric/items/Install_IsFabricReadyForIQ.Notebook`](./fabric/items/Install_IsFabricReadyForIQ.Notebook) —
  a one-click installer notebook that clones [`cyphou/FIQA`](https://github.com/cyphou/FIQA)
  into a temporary local checkout, deploys every Fabric item into the target workspace via
  REST, and deletes the checkout — no credentials, connection strings, or tenant
  identifiers are read from or written to the GitHub repository at any point. See the
  "🔐 Confidentiality Guarantees" section of [`docs/INSTALL.md`](./docs/INSTALL.md) and its
  enforcement test, [`tests/test_installer.py`](./tests/test_installer.py).
- [`fabric/items/IsFabricReadyForIQ.SemanticModel`](./fabric/items/IsFabricReadyForIQ.SemanticModel) —
  a Direct Lake model over the Gold `Mart*` Delta tables (no import, no refresh schedule
  to manage).
- [`fabric/items/IsFabricReadyForIQ.Report`](./fabric/items/IsFabricReadyForIQ.Report) — a
  Power BI report (not HTML) styled after Fabric Capacity Analysis (FCA) / FUAM report
  conventions: tenant posture, workspace ranking, blocking findings, backlog by owner,
  coverage and freshness pages.
- [`fabric/items/Fabric_IQ_Readiness_Orchestration.DataPipeline`](./fabric/items/Fabric_IQ_Readiness_Orchestration.DataPipeline)
  scheduling [`fabric/items/Fabric_IQ_Readiness_Assessment.Notebook`](./fabric/items/Fabric_IQ_Readiness_Assessment.Notebook),
  which writes the Gold marts as Delta tables into
  [`fabric/items/FabricIQReadiness.Lakehouse`](./fabric/items/FabricIQReadiness.Lakehouse) —
  closing Roadmap Sprint 4.1.

**Validation**
- First live end-to-end run against a real Microsoft 365 developer tenant
  (`tenant identity redacted`, F2 capacity), confirming the transport, the
  Scanner normaliser, the `/admin/capacities` join, and correcting three beliefs that had
  only been assumed — see [`docs/KNOWN_LIMITATIONS.md` §1.1](./docs/KNOWN_LIMITATIONS.md#11-what-the-first-live-validation-established).
- Formal self-assessment gate for the readiness semantic model/report. The synthetic
  fixture in [`examples/fiqa_self_assessment`](./examples/fiqa_self_assessment) and
  [`tests/test_self_assessment.py`](./tests/test_self_assessment.py) enforce that both
  FIQA artifacts remain `READY`, eligible, ≥85 scored, ≥90% confident/covered and free of
  blocking findings. See [`docs/SELF_ASSESSMENT.md`](./docs/SELF_ASSESSMENT.md).

**Tests** — grown from 138 to **256 tests**, all green.

### Documentation

- [`docs/ROADMAP.md`](./docs/ROADMAP.md) — Phase 1 marked done and field-validated;
  Phase 4 marked done after scheduling, Delta persistence, semantic model/report,
  AI-readable summary, trend/regression, remediation burn-down, CI gate and
  self-assessment all shipped.
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md), [`fabric/README.md`](./fabric/README.md) —
  updated to describe the deployed semantic model, report and installer notebook, which
  were previously undocumented.
- Rule count corrected from 61 to 65 wherever it appeared stale.

## [0.1.0] — 2026-09-21

First working engine. Runs end to end against synthetic fixtures.

### Added

**Scoring engine**
- Three-result contract: eligibility, readiness score (0–100), confidence
- Severity caps: blocking → 39 and ineligible, major → 59; caps only ever lower a score
- `NOT_EVALUATED` as a first-class outcome, distinct from failure and from out-of-scope
- Dimension weight renormalization over observed dimensions, so an unobservable
  dimension lowers confidence rather than score
- Coverage floor at 50%: below it an object publishes `NOT_EVALUATED`, not a score
- Workspace and tenant rollups, with a blocking child capping its parent at 59

**Rule catalogue** — 61 rules, ruleset `2026.09.1`
- `TEN-001` … `TEN-010` — tenant switches, capacity eligibility, cross-geo, scan coverage
- `WKS-001` … `WKS-009` — capacity backing, governance, lifecycle, ownership
- `SEM-001` … `SEM-017` — star schema, descriptions, synonyms, AI data schema,
  AI instructions, verified answers, RLS, freshness, schema retrieval
- `REP-001` … `REP-010` — business purpose, measure exposure, model linkage, maintenance
- `AGT-001` … `AGT-015` — source limits, instructions, accuracy, refusal behaviour,
  persona isolation, language coverage, use-case fit

**Collection**
- Medallion Bronze/Silver/Gold with hashed, timestamped evidence records
- `OfflineCollector` for fixtures; `FabricApiCollector` contract with documented quotas
  and injected transport
- `CollectionResult.validate()` as the Silver boundary; collection errors surface as
  reduced coverage rather than silent gaps

**Output**
- Prioritised remediation backlog: severity × object leverage × effort, with owner role
  and day estimates; JSON and CSV export
- Six Gold marts, every row carrying `run_id`; idempotent per-run writes
- Console and HTML reports with escaped interpolation

**Preceptorship loop**
- Six-dimension review of the assessment itself: evidence completeness, rule coverage,
  blocking integrity, remediation actionability, score traceability, freshness
- 4★ threshold, maximum 3 cycles, early exit on an unchanged coaching signature,
  escalation with publish-with-caveats or block

**Multi-agent environment**
- 13 agents with declared file ownership, shared project rules, delegation guides
- `scripts/check_agent_ownership.py` and `tests/test_agents.py` fail the build on drift

**Documentation**
- `docs/ROADMAP.md` — six phases with executable exit gates
- `docs/SCORING.md`, `docs/ARCHITECTURE.md`, `docs/AGENTS.md`, `docs/KNOWN_LIMITATIONS.md`
- `docs/RULES.md` generated from the registry by `scripts/build_rules_doc.py`

**Tests** — 138 tests covering caps, renormalization, coverage floor, rule degradation
without evidence, preceptor escalation, backlog actionability, Gold mart integrity,
CLI exit codes, agent ownership, and documentation claim accuracy.

### Fixed during development

- Duplicate measure detection ignored whitespace variants such as `SUM(T[A])` versus
  `SUM( T[A] )`. DAX is now normalized with string literals preserved, so
  `"North America"` and `"NorthAmerica"` stay distinct.
- `MartRemediationBacklog` rows carried no `run_id`, making the backlog impossible to
  join to its run in the Lakehouse.
- `ReviewScorecard.set()` accepted star ratings outside 0–5, silently corrupting the
  review average and therefore the verdict.
- `CoachingItem` silently reassigned an unknown dimension to `@orchestrator` instead of
  surfacing the programming error.
- A coaching item could be emitted with an empty location, leaving nothing to act on.

### Known limitations

Live tenant collection is a contract with an injected transport, not an implementation.
No output is currently a real tenant assessment. See
[docs/KNOWN_LIMITATIONS.md](./docs/KNOWN_LIMITATIONS.md) before quoting any result.
