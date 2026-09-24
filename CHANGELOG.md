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
  beyond `fabric_iq/` modules to documentation that asserts a privacy, identity,
  retention or collection-capability claim, and to the files a model reads as
  instruction. Seven such documents and skills now name exactly one accountable owner —
  [`docs/IDENTITY_AND_RETENTION.md`](./docs/IDENTITY_AND_RETENTION.md),
  [`docs/INTERPRETING_RESULTS.md`](./docs/INTERPRETING_RESULTS.md) and
  [`.github/skills/fabric-iq-readiness/SKILL.md`](./.github/skills/fabric-iq-readiness/SKILL.md)
  (**@readme**), [`docs/API_REALITY_MATRIX.md`](./docs/API_REALITY_MATRIX.md)
  (**@collector**), [`docs/INSTALL.md`](./docs/INSTALL.md) and
  [`fabric/README.md`](./fabric/README.md) (**@orchestrator**), and
  [`docs/SELF_ASSESSMENT.md`](./docs/SELF_ASSESSMENT.md) (**@preceptor**). The check also
  fails when a required document is missing from the repository entirely, so the
  guarantee cannot be satisfied by deleting the document that carries it.
  **@security** reviews all seven and owns no file by design: a reviewer
  that can edit what it reviews eventually reviews its own edits.
- Both checks fail with exit code `1` and name the offending path, and both carry
  negative tests over synthetic fixtures — a temporary git repository for the sink check,
  a temporary agent roster for the ownership check — proving each invariant actually
  rejects a missing ignore rule, a shadowed tracked file, a planted identifier, and a
  document that is unclaimed, doubly claimed, claimed by the wrong agent, or absent.
- CI ([`.github/workflows/ci.yml`](./.github/workflows/ci.yml)) runs the evidence-sink
  check alongside the ownership and rule-documentation checks.

**Tests** — grown from 138 to **379 tests**, all green. One test skips by design on
Windows — it plants a control character in a tracked filename to prove the NUL-separated
`git ls-files -z` parse, and Windows refuses such a name; it carries its weight on Linux
CI.

### Fixed

**Evidence-sink gate — four fail-open defects**, found by `@change-preceptor` reading
[`scripts/check_evidence_sinks.py`](./scripts/check_evidence_sinks.py) rather than running
it. Each reported a safety that was not there, and each is now pinned by a regression in
[`tests/test_evidence_sinks.py`](./tests/test_evidence_sinks.py):
- A documented output folder written with a **trailing slash** was discarded as prose
  before it ever reached the gate: the separator test ran on the stripped candidate, and
  `"/" in "results/".strip("/")` is `False`. A single-level destination documented that
  way was never checked against any ignore rule. The separator is now tested on the raw
  value, and only a candidate that is nothing but separators is treated as naming no
  destination.
- Tracked files with **non-ASCII names** were invisible to *both* the shadowing check and
  the identifier scan. Under git's default `core.quotePath`, `docs/café.md` comes back as
  an octal C-literal that opens nothing and matches no ignore rule, so a real-shaped
  synthetic GUID planted in that file went unreported while its ASCII twin was caught.
  Git is now run with `-c core.quotePath=false`, the index is read with
  `git ls-files -z`, and a pathname `git check-ignore` echoes back that was not asked for
  raises instead of being silently dropped.
- **Non-UTF-8 files were skipped as "binary"** although they leak exactly like their
  UTF-8 twin — a UTF-16 document is text. Tracked bytes are now read in binary and
  decoded losslessly, with NUL bytes stripped so ASCII identifier runs reassemble in
  either endianness; a BOM-less UTF-16 file decodes as UTF-8 *without error*, so a
  fallback triggered only by a decode failure would still have missed it. A tracked file
  that cannot be **opened** is now reported by name, because an unscanned file that
  reports nothing is indistinguishable from a clean one.
- An **untracked `.gitignore` counted as protection**. Matching on the filename alone
  accepted a rule source that exists in one clone and can be deleted, or simply never
  exist for a teammate, while the gate reported the tree as safe. The ignore source is
  now intersected with the index, alongside the existing rejections of an absolute
  source, a blank CRLF pattern, and a negation rule that re-includes the destination.

The identifier scan additionally now flags an **undashed** 32-hex tenant id — the form a
token claim carries — bounded so a 40-hex commit SHA does not match, and skips a gitlink
directory, whose own checkout runs its own gate.

**Ownership audit — `scripts/` was outside the audited universe.** The check built its
universe from the modules under `fabric_iq/` plus `REQUIRED_DOCS`, so the two gate scripts
`@tester` claims were parsed but never verified, and `scripts/build_rules_doc.py` and
`scripts/__init__.py` were owned by nobody. The universe is now `fabric_iq/` **plus**
`scripts/` plus the required documents — **26** audited modules and **7** documents and
skills — with the gate scripts and the package marker claimed by **@tester** and the
generator behind [`docs/RULES.md`](./docs/RULES.md) claimed by **@readme**, which owns its
output and runs `python scripts/build_rules_doc.py --check` as part of the documentation
gate. An unowned gate is worse than an unowned module: it keeps exiting `0` while the
thing it was written to catch walks past it, and no agent is accountable for noticing.

### Documentation

- [`docs/KNOWN_LIMITATIONS.md`](./docs/KNOWN_LIMITATIONS.md) §8 "Product Limits Age" —
  all eight encoded product limits individually re-verified 2026-09-24 against live
  Microsoft Learn / REST API reference pages (fetched, not just link-resolved as on
  2026-09-23), closing the product-fact-verification half of the Phase 5 Sprint 5.3
  release gate. Three source links corrected to the page that actually states the
  quoted fact rather than a generic page that only links out to it or omits the number
  entirely: `SEM-006`/`SEM-007` (200-character description budget) and `SEM-011`
  (10,000-character AI-instruction max) now cite the specific Power BI Copilot
  documentation pages/anchors; `TEN-012` (Purview DLP/access-restriction GA vs. preview
  split) and the Scanner `getInfo` rate-limit constants (500/hour, 16 concurrent, 100
  workspaces/request) now cite the pages that actually state those facts. No rule value,
  threshold, or test fixture changed — sourcing and dating only. The Sprint 5.3
  calibration sub-criterion (blinded practitioner labelling, owned by `@scorer`) remains
  open and is unaffected by this change.
- [`docs/ROADMAP.md`](./docs/ROADMAP.md) — Phase 2 exit gate, the Sprint 5.3 entry, the
  Phase 5 release gate (criterion 2), and the sequencing notes reconciled to reflect that
  product-limit sourcing/dating closed 2026-09-24 while calibration remains open, so the
  sprint and phase are not misrepresented as either fully closed or fully unstarted.
- [`.github/skills/fabric-iq-readiness/SKILL.md`](./.github/skills/fabric-iq-readiness/SKILL.md) —
  the "What To Check, By Level" preamble and the tenant-capacity-floor callout updated
  from "source candidate link resolved 2026-09-23, fact verification open" to reflect
  the 2026-09-24 confirmation, without claiming this Skill is itself a source of
  Microsoft fact — it still routes to `docs/KNOWN_LIMITATIONS.md` §8.
- [`docs/INTERPRETING_RESULTS.md`](./docs/INTERPRETING_RESULTS.md) (new) — the
  operational guide to reading a run, written for a human at a console rather than for a
  model. It moves the interpretation knowledge that previously existed only in
  AI-facing files (`.github/skills/`, `.github/agents/`) into the documentation set:
  the reading order (blocking findings, then `NOT_EVALUATED`, then scores beside their
  confidence, then backlog), what each console column and section means, a triage table
  from result pattern to first move, the `NOT_EVALUATED` instruction ("fix collection,
  do not re-score") with the command that lists which rules went unread, and the results
  that surprise people — over-broad AI data schemas, agent instructions that cannot fix
  model metadata, endorsement as self-attestation, and refusal as a security property.
  Every claim was reproduced against ruleset `2026.09.1` before being written; the
  normative thresholds stay in [`docs/SCORING.md`](./docs/SCORING.md) and the rule detail
  in the generated [`docs/RULES.md`](./docs/RULES.md), which this guide links rather than
  restates.
- [`README.md`](./README.md) — a "Reading the results" section links the new guide, so a
  reader who never loads a Skill still finds it.
- [`.github/skills/fabric-iq-readiness/SKILL.md`](./.github/skills/fabric-iq-readiness/SKILL.md) —
  now **routes** to `docs/INTERPRETING_RESULTS.md` instead of being the only home of the
  interpretation knowledge. The Skill keeps a usable summary (and every engine-constant
  claim the drift check asserts), and is explicitly told to send users to the guide. The
  Skill is optional sugar; the CLI and the documentation stand alone.

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
- [`docs/AGENTS.md`](./docs/AGENTS.md), [`README.md`](./README.md) and
  [`.github/copilot-instructions.md`](./.github/copilot-instructions.md) — document the
  **two-role oversight model** and the fourteenth agent, `@change-preceptor`. Development
  work runs **Plan → Assign → Implement → Review**: `@orchestrator` is the tech lead that
  plans and assigns, the eleven file-owning specialists implement, and `@change-preceptor`
  reviews a change before it lands. It owns no file — like `@security`, a reviewer that
  can edit what it reviews eventually reviews its own edits — and it coaches the owning
  agent rather than fixing the code. The roster documentation is explicit that **two
  agents carry the word "preceptor" and are not the same role**: `@preceptor` reviews the
  **assessment** a run produced (a product feature behind `--review`, pinned by
  `tests/test_preceptor.py`), while `@change-preceptor` reviews a **code change** and
  ships no code. The section records why the role exists — four gates that *failed open*
  in one session, each now pinned by a regression: a required document missing entirely
  while the ownership check exited 0, a CRLF blank line in `.gitignore` matching every
  directory so the sink check passed on nothing, a dot-leading path the claim parser
  could not read so an ownership claim was invisible, and a locally-green commit that
  went red on the four gates CI runs beyond the unittest suite. The existing
  preceptorship section is retitled "The Assessment Preceptorship Loop — `@preceptor`"
  so a reader knows which preceptor it belongs to.
- [`docs/AGENTS.md`](./docs/AGENTS.md) — the audited universe is described as **three**
  populations (the 22 modules under `fabric_iq/`, the 4 scripts under `scripts/`, the 7
  documents and skills), the roster records who owns each script, and a new
  "Script ownership — the gates and the generator" table states the split: `@tester` owns
  the checks that fail the build, `@readme` owns the generator whose output is a
  published document, and rule *content* stays with the rule's owning agent.
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

- **Evidence handling: live runs now write outside the repository.**
  [`docs/IDENTITY_AND_RETENTION.md`](./docs/IDENTITY_AND_RETENTION.md) documents the
  practice and the reasoning behind it, after a privacy audit of a user-authorised,
  read-only live proof. The audit returned **CONTAINED** — no tenant identifier reached
  any tracked file, the index, or the repository's history — and surfaced that the
  guarantee everyone was relying on was the wrong one: *git-ignored is not share-safe*.
  An ignore rule only stops git from offering to commit a file; it stops nothing that a
  zip, a shared or synced directory, a backup sweep or a workspace-indexing editor does.
  Three new or hardened pieces:
  - §3.1.1 states the distinction, and that `artifacts/` inside the checkout is for
    **synthetic output only**. The rendered `_readiness.html` is called out as the
    artifact most likely to escape, precisely because it is the one built to be shown.
  - §3.5 describes the external evidence store (`<date>_<purpose>` folders outside both
    the working tree and any synced folder, carrying their own `README.md` with the
    handling rules and a per-run expiry table), and records that a full
    `--inventory … --review --out …` run was executed end to end with both paths outside
    the repository — all five artifacts, HTML included, written there and nothing created
    in the checkout. It also states what the practice does *not* buy: no gate, including
    `check_evidence_sinks.py`, can see a path outside the repository.
  - §3.3 turns the checkpoint rule into a warning callout instead of a bullet, because it
    was breached: a checkpoint survived three days past the run it resumed, holding a
    tenant identifier, UPNs across two real domains and raw admin Bronze payloads. It
    also records **@security**'s standing recommendation, now practice — *a live run gets
    its expiry date at authorisation, not afterwards*, written into the store's `README.md`
    before the first call is made.
  Acted on at the same time, and described here as the reason the rules changed: the
  breaching checkpoint, the live run outputs carrying real UPNs, the rendered readiness
  reports and two duplicate run triplets were destroyed; `artifacts/` was verified to
  hold synthetic output only; the surviving raw evidence carries a dated expiry.
- [`docs/KNOWN_LIMITATIONS.md`](./docs/KNOWN_LIMITATIONS.md) §1.4 (new) — what a
  read-only live read established about the **read surfaces themselves**, published as
  ratios with no estate size, workspace name, identifier, portal link or host:
  `capacityId` returned `null` for **100%** of workspaces on the OneLake listing surface,
  so no capacity-dependent rule is evaluable from it; that listing and the catalog search
  returned **disjoint** workspace sets (**0%** overlap by GUID *and* by name), so a
  single-surface collector misses the other population entirely rather than seeing a
  subset of it; workspace `id` on that surface is an **opaque non-GUID string**, so the
  two surfaces cannot be joined on identity; **no Data Agent item type** was exposed; and
  **no tenant admin settings** were reachable through that session, leaving every
  tenant-switch rule `NOT_EVALUATED` on that path. The consequence recorded is that which
  read surface a collector uses changes which rules are evaluable at all — the case where
  "the collector ran" reads as "the tenant was read". The endpoint-by-endpoint detail is
  cross-linked to [`docs/API_REALITY_MATRIX.md`](./docs/API_REALITY_MATRIX.md) rather than
  duplicated, because two availability tables drift and the stale one is the one quoted.
- [`docs/AGENTS.md`](./docs/AGENTS.md) — `docs/API_REALITY_MATRIX.md` is claimed by
  **@collector** in the roster and in the documentation-ownership table, which is retitled
  to cover a **collection-capability** claim alongside privacy, identity, retention and
  instruction. A statement about what the collectors cannot read is a claim about the
  engine's own blind spots, and a stale row in it reads as evidence that was never
  collectable. The audited documentation set is **7** documents and skills, reproduced
  from `python scripts/check_agent_ownership.py`; the module count is unchanged at **26**.
- [`README.md`](./README.md) — reconciled against the above: the gate paragraph now says
  seven documents and skills and names the collection-capability claim; a new callout
  states that git-ignored is not share-safe and that `artifacts/` is synthetic-only; the
  live-run example writes its `--out` and `--checkpoint` to an external evidence store
  instead of `artifacts/`, and tells the operator to delete the checkpoint as soon as the
  scan it resumes has finished; and the Power BI warning notes that the committed ignore
  rule protects the in-repository default only.

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
