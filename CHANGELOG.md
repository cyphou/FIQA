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
- First live end-to-end run against a real Microsoft 365 developer tenant on F2
  capacity (tenant identity redacted), confirming the transport, the
  Scanner normaliser, the `/admin/capacities` join, and correcting three beliefs that had
  only been assumed — see [`docs/KNOWN_LIMITATIONS.md` §1.1](./docs/KNOWN_LIMITATIONS.md#11-what-the-first-live-validation-established).
- Formal self-assessment gate for the readiness semantic model/report. The synthetic
  fixture in [`examples/fiqa_self_assessment`](./examples/fiqa_self_assessment) and
  [`tests/test_self_assessment.py`](./tests/test_self_assessment.py) enforce that both
  FIQA artifacts remain `READY`, eligible, ≥85 scored, ≥90% confident/covered and free of
  blocking findings. See [`docs/SELF_ASSESSMENT.md`](./docs/SELF_ASSESSMENT.md).

**Evidence hygiene and documentation ownership** — two release gates made executable
- [`scripts/check_evidence_sinks.py`](./scripts/check_evidence_sinks.py) with
  [`tests/test_evidence_sinks.py`](./tests/test_evidence_sinks.py) — asserts that every
  writer destination (defaults, emitted extensions, and the `--out`, `--lakehouse`,
  `--powerbi` and `--checkpoint` values used as examples in tracked documentation and
  code) resolves to a rule in a committed `.gitignore`; that no tracked file is shadowed
  by those rules, so every tracked file stays trackable; and that no tracked file carries
  a real tenant identifier, UPN, email address, `onmicrosoft` host or non-placeholder
  GUID. Prompted by a privacy audit that found a documented command writing
  tenant-derived CSVs to a path no committed ignore rule covered. The check is a
  heuristic gate over this repository: it reduces, and never replaces, the mandatory
  pre-push privacy audit, and it cannot see a path written outside the working tree.
- [`scripts/check_agent_ownership.py`](./scripts/check_agent_ownership.py) extended
  beyond `fabric_iq/` modules to documentation that asserts a privacy, identity or
  retention claim. Four such documents now name exactly one accountable owner —
  [`docs/IDENTITY_AND_RETENTION.md`](./docs/IDENTITY_AND_RETENTION.md) (**@readme**),
  [`docs/INSTALL.md`](./docs/INSTALL.md) and [`fabric/README.md`](./fabric/README.md)
  (**@orchestrator**), and [`docs/SELF_ASSESSMENT.md`](./docs/SELF_ASSESSMENT.md)
  (**@preceptor**). **@security** reviews all four and owns no file by design: a reviewer
  that can edit what it reviews eventually reviews its own edits.
- Both checks fail with exit code `1` and name the offending path, and both carry
  negative tests over synthetic fixtures — a temporary git repository for the sink check,
  a temporary agent roster for the ownership check — proving each invariant actually
  rejects a missing ignore rule, a shadowed tracked file, a planted identifier, and a
  document that is unclaimed, doubly claimed or claimed by the wrong agent.
- CI ([`.github/workflows/ci.yml`](./.github/workflows/ci.yml)) runs the evidence-sink
  check alongside the ownership and rule-documentation checks.

**Tests** — grown from 138 to **295 tests**, all green.

### Documentation

- [`docs/IDENTITY_AND_RETENTION.md`](./docs/IDENTITY_AND_RETENTION.md) reconciled against
  the writers: all **four** run destinations are now documented (`--out`, `--lakehouse`,
  `--powerbi`, `--checkpoint`) with what each contains and which writer produces it,
  where previously only the medallion output was named; the medallion extension is
  corrected to `.jsonl` (the protection is a filename pattern, so `.ndjson` would have
  left Bronze evidence trackable); the `--checkpoint` file is called out as the most
  identity-dense artifact a run leaves behind; and the 30–90 day Bronze retention figure
  is restated as an operational recommendation made in that document, its attribution to
  a `KNOWN_LIMITATIONS.md` source removed because no such source existed.
- [`README.md`](./README.md) — documents `python scripts/check_evidence_sinks.py` and
  what each gate asserts, so the documented gate set matches the one CI runs.
- [`docs/ROADMAP.md`](./docs/ROADMAP.md) — Phase 1 marked done and field-validated;
  Phase 4 marked done after scheduling, Delta persistence, semantic model/report,
  AI-readable summary, trend/regression, remediation burn-down, CI gate and
  self-assessment all shipped.
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md), [`fabric/README.md`](./fabric/README.md) —
  updated to describe the deployed semantic model, report and installer notebook, which
  were previously undocumented.
- Rule count corrected from 61 to 65 wherever it appeared stale.
- [`.github/skills/fabric-iq-readiness/SKILL.md`](./.github/skills/fabric-iq-readiness/SKILL.md) —
  the agent-facing Skill is now claimed by **@readme** and reconciled against the engine:
  every restated threshold (5 data sources, 25×25, 200-character description budget,
  10,000-character AI instructions, ≥ 85% / ≥ 95% accuracy, the 39/59 caps, the 50%
  coverage floor) was verified against its constant and is now labelled as
  ruleset-encoded, with the reader routed to the generated `docs/RULES.md` and to the
  dated product-limit table in `docs/KNOWN_LIMITATIONS.md` §8. The undated
  "Power BI Q&A retires in December 2026" claim is replaced by the verifiable statement
  that no rule depends on Q&A and that its retirement timing is unverified here. The
  command list now teaches the current gate set, including
  `python scripts/check_evidence_sinks.py` and documentation ownership.

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
