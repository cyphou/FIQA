# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
