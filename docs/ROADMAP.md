# Roadmap — IsFabricReadyForIQ

Owner: **@roadmap-planner**. This document is authoritative for scope and release gates.

Last evidence review: **2026-09-23** against ruleset `2026.09.1`.

## Purpose

Tell an organisation, with evidence, whether its Power BI / Fabric estate is ready for
Fabric IQ and agentic experiences — and exactly what to change, object by object.

## Non-Negotiable Contract

Every increment and release gate preserves these constraints:

- Collection is read-only. The assessor reports; it never changes a tenant.
- Missing evidence produces `NOT_EVALUATED`, never a pass or a zero. If coverage is
  below 50%, status is `NOT_EVALUATED`; the computed score remains visible but is not a
  readiness verdict.
- A blocking failure revokes eligibility and caps score at 39. A major failure caps at
  59. Caps only lower scores.
- Eligibility, readiness score, and confidence are separate results and are never
  merged or substituted for one another.
- The core engine uses the Python standard library only.
- Repository fixtures and examples are synthetic. Tenant-derived evidence is never
  committed at **any** output path. `artifacts/` is the conventional sink, not the
  boundary: every writer, CLI output flag, and documented example must resolve to an
  ignored location, including at values a user supplies.
- API-dependent work starts with a real-tenant proof of the read surface. Collection
  gaps are not hidden by scoring or presentation changes.

## Evidence-Based Development State

The status below reflects executable repository evidence and bounded live-validation
records, not earlier roadmap labels.

| Area | Delivered evidence | Remaining gap | Status |
|------|--------------------|---------------|--------|
| Contract and offline pipeline | Scoring, rollups, remediation, preceptorship, medallion output, and CLI run end to end on `examples/sample_tenant`; scoring regressions cover caps, coverage, and independent results. | None for the synthetic/offline scope. | ✅ Delivered |
| Rule catalogue | `python assess.py --list-rules` reports 65 rules: tenant 12, workspace 11, semantic model 17, report 10, Data Agent 15. | Encoded product limits do not yet all carry a source and exact re-verification date. | 🟡 Partially evidenced |
| Live collection | `FabricHttpTransport`, Scanner `getInfo`, pagination, bounded 429 retry, Bronze evidence, checkpoint resume, and read-only request validation are implemented and tested. Recorded live runs validate the transport, Scanner normalisation, capacity join, and both pipeline gate branches. | Complete field coverage is not validated. Prep-for-AI, AI instructions, verified answers, Data Agent definition/source fields, relationships, and some capacity signals remain unconfirmed or unavailable. Live Scanner evidence evaluates roughly 8 of 17 semantic-model rules. | 🟡 Partial field coverage |
| Scale and incrementality | Synthetic tests cover proactive per-process quota handling, interrupted-run resume, and honest partial coverage for 500 workspaces. | Scans are sequential; quota state is not tenant-wide; `modified_since_days` is not wired to incremental scanning. These are explicit limitations, not delivered capabilities. | 🟡 Bounded |
| Scoring and backlog | Explainable scorecards, CSV/JSON backlog, owner role, effort, trend classification, and remediation burn-down are implemented and tested. | Weights and thresholds have not been calibrated against independently labelled real objects. Product-limit verification remains open. | 🟡 Calibration open |
| Data Agent readiness | Fifteen static rules consume supplied evidence and degrade missing inputs to `NOT_EVALUATED`. | No harness executes a corpus against a real agent; behavioural accuracy, refusal, latency, and persona isolation are therefore not measured by this repository. | 🟡 Static only |
| Fabric publication | Notebook, Data Pipeline, Lakehouse, Gold Delta marts, Direct Lake semantic model/report, run summary, trends, burn-down, and CI exit gates exist. The model/report synthetic self-assessment gate is executable. | The pipeline is schedulable, but no versioned schedule/recurrence artifact or unattended monthly-run evidence exists. “Scheduled” and “unattended” are not yet delivered claims. | 🟡 Schedulable |
| Re-measurement | Comparable-run trends, automatic baseline selection, coverage-loss classification, and remediation-state comparison are implemented. | A repeatable operational cadence, ruleset-compatible baseline policy, and recorded remediation/re-measure cycle are not yet proven end to end. | 🟡 Mechanism delivered |

### Verified Repository Baseline

At this review the documentation gate reported:

- ruleset `2026.09.1`, **65 rules** across five object types;
- **256** passing unit tests;
- clean generated rule documentation, ownership audit, internal links, and synthetic
  self-assessment gate;
- an evidence-sink check after the 2026-09-23 privacy fix: **95 tracked files**, none of
  them shadowed by the hardened ignore rules, and no tenant identifier, UPN, or email
  address in tracked content outside synthetic placeholders.

These counts describe the current revision only. They are not release-quality evidence
for unconfirmed live API fields, scheduling, calibration, or real-agent behaviour.

## Phase 0 — Framing and Contract ✅

Delivered for offline/synthetic execution: the three-result scoring contract, outcome
model, severity caps, coverage floor, deterministic rule registry, remediation,
preceptorship, medallion output, and ownership model.

**Exit gate.** Met for this bounded scope: the synthetic sample runs end to end, scoring
contract regressions pass, and ownership is executable. This does not claim live-field
coverage.

## Phase 1 — Inventory and Live Collection 🟡

The standard-library transport, selected Scanner/capacity mappings, quotas, checkpoint
resume, and read-only enforcement are implemented. Transport and selected fields were
field-validated; complete API availability and SKU coverage remain open and move to
Sprints 5.1–5.2.

**Exit gate.** Open: every rule input must have a field-level availability
classification, with unsupported evidence producing `NOT_EVALUATED`.

## Phase 2 — Static Readiness Scoring 🟡

The engine, 65-rule catalogue, actionable backlog, and output formats are delivered.
Product-limit sourcing and practitioner calibration remain open and move to Sprint 5.3.

**Exit gate.** Open: every encoded limit has a public source and exact verification
date, and calibration disagreements are recorded without tenant-specific tuning.

## Phase 3 — Agentic Readiness 🟡

Fifteen static Data Agent rules consume supplied metrics. No repository harness executes
a corpus against a real agent, so behavioural readiness is not yet measured.

**Exit gate.** Open: the execution surface is proved before implementation and a
supplied corpus produces reproducible per-persona metrics, or unavailable evidence stays
explicitly `NOT_EVALUATED`.

## Phase 4 — Industrialisation 🟡

Pipeline execution, Delta persistence, the semantic model/report, trends, remediation
burn-down, self-assessment, and CI gates are delivered. The pipeline is schedulable, but
a versioned schedule and two-run unattended re-measurement cycle are not proven.

**Exit gate.** Open: two ruleset-compatible unattended runs demonstrate scheduling,
reviewed publication, compatible baseline selection, trend classification, and burn-down.

Prior implementation remains useful; correcting a completion label does not remove it.
The next phase closes the evidence chain rather than adding unsupported breadth.

---

## Phase 5 — Evidence Closure and Repeatable Re-Measurement

**Outcome.** A target tenant can be assessed with a field-level statement of what was
observed, operated on a defined cadence, and re-measured without turning blind spots
into verdicts.

**Concrete anchor.** [`docs/KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) records partial
live validation while Prep-for-AI, AI instructions, verified answers, and Data Agent
metadata remain unconfirmed; the repository also has a Data Pipeline but no schedule
artifact.

**Falsifiable hypothesis.** The required read-only metadata is either available from
documented tenant surfaces with stable field shapes, or can be classified explicitly as
unavailable so affected rules remain `NOT_EVALUATED`.

**Cheap check.** Before changing a collector or rule, issue the minimum read-only calls
for one authorised workspace and record a redacted field matrix:
`available / partial / absent / permission-blocked / preview-only`. No customer payload
is committed.

**Exit gate.** All ten criteria in **Release Gate for Phase 5** are met; in particular,
unsupported evidence remains `NOT_EVALUATED`, no output path can place tenant-derived
evidence under version control, and two compatible unattended runs prove the complete
re-measurement loop.

### Sprint 5.0 — Evidence-Sink and Provenance Hygiene (fix delivered; two decisions open)

1. **Outcome** — No tenant-derived evidence can reach version control through any
   documented command, writer default, or CLI output flag, and every file that makes a
   privacy, identity, or retention claim has a named accountable owner.
2. **Current evidence** — A `@security` audit on 2026-09-23 found that the documented
   `assess.py --inventory <inv> --powerbi ./powerbi_report` wrote object and workspace
   names, scores, and findings into `powerbi_report/`, which was not git-ignored, so a
   `git add .` after a live run would have committed tenant-derived evidence. The same
   audit found `--out`, `--lakehouse`, and `--checkpoint` safe only at their documented
   default values; `--checkpoint` persisting `tenant_id` and raw Bronze payloads
   including `identity`; `.gitignore` ignoring `*.ndjson` while the writer emits
   `.jsonl`; and a real tenant admin UPN committed to `CHANGELOG.md` and pushed. The
   ignore rules, CLI help warnings, and forward redaction are fixed and verified — 95
   tracked files with none shadowed, 256 tests passing. Separately,
   `scripts/check_agent_ownership.py` audits only modules under `fabric_iq/`, so
   [`IDENTITY_AND_RETENTION.md`](IDENTITY_AND_RETENTION.md), [`INSTALL.md`](INSTALL.md),
   [`SELF_ASSESSMENT.md`](SELF_ASSESSMENT.md), and `fabric/README.md` are claimed by no
   agent.
3. **Smallest slice** — Two remaining slices. (a) `@security` prepares the
   authorised-human decision on the pushed history that still contains the UPN, together
   with the retention disposition of the local `artifacts/checkpoint.json` holding a real
   tenant GUID; neither is an agent action. (b) `@tester` extends the ownership audit, or
   adds a sibling check, so a documentation file asserting a privacy, identity, or
   retention claim fails the build when no agent claims it; `@readme` and the named
   owners then claim the four unowned files.
4. **Dependencies** — `@security` owns the privacy verdict, scopes, and retention;
   `@orchestrator` owns CLI help text and output-flag defaults; `@tester` owns the
   executable ownership and scan checks; `@readme` owns documentation ownership
   declarations. The history rewrite is a user decision. No later sprint may introduce a
   writer whose default or documented path is trackable.
5. **Validation** — Focused check: `git check-ignore -v` resolves every writer default
   and every documented output example to a rule, and the tracked-file identifier scan in
   the **Per-Change Quality Gate** returns only synthetic placeholders. Release gate:
   criteria 9 and 10 below.
6. **Risks and non-goals** — Ignore rules do not remove data already pushed; only an
   authorised history rewrite does, and that decision is open. The scans are heuristics
   that reduce, never replace, the mandatory pre-push privacy audit. This sprint does not
   add redaction to collected evidence, does not weaken checkpoint resume, and does not
   claim the pushed history is clean.
7. **Commit boundary** — Ignore rules, CLI help text, and their verification belong with
   the delivered orchestrator/security change. The ownership-audit extension and the four
   documentation ownership declarations form a separate `@tester`/`@readme` boundary.
   The `artifacts/` disposition produces no commit.

### Sprint 5.1 — Close the API Reality Matrix (3–5 days)

1. **Outcome** — Every field consumed by the 65-rule catalogue has a current,
   reproducible availability classification, including the fields still unconfirmed
   after the first live run.
2. **Current evidence** — Live evidence validates the transport, Scanner normaliser,
   capacity join, and roughly 8 of 17 semantic-model rules. The availability record is
   incomplete for Prep-for-AI, AI instructions, verified answers, Data Agent
   definition/sources, model relationships, and capacity throttling.
3. **Smallest slice** — `@collector` runs a one-workspace, read-only proof and prepares a
   field-to-endpoint matrix with HTTP outcome, required scope, SKU/preview qualification,
   and redacted evidence reference. `@security` reviews scopes and retention before the
   proof. `@readme` reconciles the resulting bounded claims in README and known
   limitations.
4. **Dependencies** — Authorised test tenant and service principal; `@collector` owns
   acquisition; `@security` owns least privilege and provenance; `@readme` owns the
   documentation outside this roadmap. No implementation sprint may assume a field that
   this proof does not confirm.
5. **Validation** — Focused check: rerun the proof and reproduce each matrix
   classification without persisting raw payloads in git. Release gate: every rule input
   maps to a confirmed field or an explicit unavailable/preview classification, and
   unconfirmed inputs still produce `NOT_EVALUATED`.
6. **Risks and non-goals** — Tenant/SKU variance may prevent a universal claim. This
   sprint does not add endpoints, weaken rules, infer absent values, or claim that one
   tenant represents all SKUs.
7. **Commit boundary** — Collector-owned proof/fixture changes and tests form one commit;
   Security/Readme-owned scope and availability documentation form a separately reviewed
   documentation commit. No live payload or identifier is included.

### Sprint 5.2 — Reconcile Collection and Rule Coverage (1–2 weeks)

1. **Outcome** — Confirmed fields are normalized and evaluated; unavailable fields
   remain visible blind spots with correct object-level confidence.
2. **Current evidence** — The collector already degrades unreadable and absent evidence,
   while the live record shows material semantic-model evidence gaps. Existing synthetic
   tests cover quota, resume, and partial-batch coverage.
3. **Smallest slice** — Select one field family confirmed by Sprint 5.1, add its
   normalization and synthetic contract fixture, then activate only the rules that can
   consume it without inference. Repeat field family by field family; permanently
   unavailable inputs stay `NOT_EVALUATED`.
4. **Dependencies** — `@collector` owns transport/normalization/fixtures; `@semantic`,
   `@tenant`, or `@dataagent` owns the affected rule; `@tester` owns cross-boundary
   regressions; `@scorer` reviews any shared-model impact. Sprint 5.1 is a hard
   prerequisite.
5. **Validation** — Focused check: for each new field family, synthetic present, absent,
   null, forbidden, and malformed cases produce the expected evidence and rule outcome.
   Release gate: full test suite passes; no missing input passes or fails; confidence
   falls when applicable evidence is missing; blocking failures still cap at 39 and
   revoke eligibility.
6. **Risks and non-goals** — API shapes may vary or remain preview-only. The sprint does
   not compensate for collection gaps by changing weights, caps, thresholds, or report
   visuals, and it does not automate remediation.
7. **Commit boundary** — One confirmed field family, its normalizer, synthetic fixtures,
   owned rules, and focused tests belong together. Do not bundle unrelated rule growth
   or presentation changes.

### Sprint 5.3 — Verify Product Facts and Calibrate Verdicts (1 week plus field review)

1. **Outcome** — Encoded limits are dated facts, and any proposed scoring change is
   supported by practitioner disagreement evidence rather than intuition.
2. **Current evidence** — The catalogue and scoring engine are executable, but the
   documented limits lack complete source/date records and current weights have not been
   compared with independently labelled real objects.
3. **Smallest slice** — `@readme` records a public source and exact `YYYY-MM-DD`
   verification date for each encoded limit. In parallel, `@scorer` defines a blinded
   calibration worksheet; two practitioners independently label a bounded 20–30 object
   sample without seeing tool scores.
4. **Dependencies** — `@readme` owns limit documentation; domain rule owners confirm rule
   interpretation; `@scorer` owns calibration and any maths proposal; `@security`
   approves de-identification and retention. Sprint 5.2 supplies honest coverage.
5. **Validation** — Focused check: a documentation test fails when an encoded limit lacks
   a source/date; calibration records agreement and every disagreement. Release gate:
   limits are current and traceable; any weight/threshold change has rationale,
   scorer sign-off, regression tests, and ruleset-version handling. No change is required
   merely to increase agreement.
6. **Risks and non-goals** — A small sample cannot establish universal validity and must
   not be tuned to improve one tenant. This sprint does not merge confidence into score,
   relabel `NOT_EVALUATED`, or alter blocking cap 39.
7. **Commit boundary** — Sourced limit records and their documentation gate are one
   boundary. Each accepted scoring change, ruleset increment, migration note, and
   regression test is a separate scorer-owned boundary.

### Sprint 5.4 — Prove Behavioural Data Agent Evaluation (proof first, 1–2 weeks)

1. **Outcome** — The project either demonstrates a read-only, reproducible route for
   executing a supplied synthetic corpus against a real agent, or records that the
   execution surface is unavailable and keeps AGT-006…AGT-012 `NOT_EVALUATED`.
2. **Current evidence** — Fifteen static Data Agent rules accept supplied metrics, but no
   repository harness executes questions, captures generated queries, measures refusal
   or latency, or tests persona isolation.
3. **Smallest slice** — `@dataagent` and `@collector` first prove the minimum supported
   execution/readback surface with one synthetic question and one persona. Only after
   that proof, add a versioned synthetic corpus schema and one end-to-end harness case.
4. **Dependencies** — Confirmed product surface and read-only scope; `@dataagent` owns
   corpus semantics and thresholds; `@collector` owns API reality; `@security` owns
   persona/transcript handling; `@tester` owns the synthetic harness regression. This
   sprint does not start implementation on an unverified endpoint.
5. **Validation** — Focused check: repeat one question and retain reproducible,
   redacted evidence for answer/query/latency/refusal. Release gate: a supplied corpus
   produces accuracy, critical accuracy, refusal, leakage, and latency metrics per
   persona; deliberate isolation failure is blocking; unavailable evidence remains
   `NOT_EVALUATED`.
6. **Risks and non-goals** — The execution API may not exist, may be preview-only, or may
   expose customer transcript data. The tool does not author business questions, rewrite
   prompts, create agents, or claim behavioural quality from static metadata.
7. **Commit boundary** — API proof and limitation record precede implementation.
   Corpus schema plus synthetic example form one DataAgent-owned boundary; harness,
   redaction, and focused tests form the next only after the proof passes.

### Sprint 5.5 — Schedule, Publish, and Re-Measure (1 week plus cadence interval)

1. **Outcome** — An operator can reproduce an unattended read-only run, review its
   verdict, publish approved marts/report, apply human-owned remediation, and compare the
   next compatible run.
2. **Current evidence** — Pipeline execution, persistence, baseline selection, trends,
   coverage-loss classification, burn-down, self-assessment, and CI exit codes exist.
   There is no versioned schedule artifact or recorded unattended monthly cycle.
3. **Smallest slice** — `@orchestrator` and `@lakehouse` define one deployment-owned
   schedule contract with cadence, overlap prevention, identity, retention, failure
   notification, and rerun procedure; prove one unattended synthetic-safe run before
   waiting for a full monthly cycle.
4. **Dependencies** — `@orchestrator` owns run lifecycle and exit codes; `@lakehouse`
   owns persistence/reporting; `@security` reviews identity and retention; `@preceptor`
   owns review approval; `@remediation` owns the human backlog hand-off. Sprints 5.1–5.3
   establish defensible collection and scoring. Scheduler configuration may remain an
   environment-owned deployment step rather than a portable repository artifact.
5. **Validation** — Focused check: one unattended run writes a unique `run_id`, publishes
   current snapshot marts, preserves history, surfaces blocking/review failure without
   log parsing, and cannot overlap itself. Release gate: two ruleset-compatible runs
   complete on cadence; the second selects the first as baseline; trend distinguishes
   quality regression from coverage loss; burn-down shows new/open/resolved/reopened;
   preceptorship approves at ≥4★ or explicitly blocks/escalates publication.
6. **Risks and non-goals** — Scheduler definitions can be tenant-specific and live
   remediation may take longer than one cadence. Until two unattended runs exist, the
   claim remains “schedulable,” not “scheduled.” The assessor never applies the backlog
   or writes to assessed tenant objects.
7. **Commit boundary** — Schedule contract/deployment support and tests belong together;
   run evidence remains outside git. Reporting changes are separate unless required to
   expose a gate already produced by the run.

## Release Gate for Phase 5

The phase closes only when all of the following are executable or evidenced:

1. Every current rule input has a confirmed availability classification; unsupported
   inputs demonstrably remain `NOT_EVALUATED`.
2. All encoded product limits have a public source and exact verification date.
3. Full tests, generated-rule check, ownership check, documentation links, rule counts,
   and synthetic self-assessment are green.
4. Read-only enforcement is tested; no write scope or write operation is introduced.
5. Eligibility, score, and confidence remain separate; blocking cap 39, major cap 59,
   and the 50% coverage floor retain regression coverage.
6. Core runtime remains standard-library-only and all committed fixtures are synthetic.
7. Behavioural Data Agent claims are backed by a real execution proof; otherwise the
   affected rules and phase item remain explicitly `NOT_EVALUATED`/open.
8. Two ruleset-compatible unattended runs demonstrate collect → normalize → score →
   prioritise → review → publish → re-measure. If schedule evidence is unavailable, the
   phase stays open even when the pipeline can be triggered manually.
9. Evidence-sink hygiene is verified: every writer default and every documented output
   example resolves to a `.gitignore` rule under `git check-ignore -v`; no CLI output
   flag steers a user toward a trackable location at its documented value; and a
   pre-push scan of tracked content finds no tenant identifier, workspace or capacity
   GUID, UPN, or email address outside synthetic placeholders.
10. Every documentation file that makes a privacy, identity, or retention claim is
    claimed by exactly one agent and covered by an executable ownership check.

## Sequencing and Release Policy

`5.0 evidence-sink hygiene → 5.1 API proof → 5.2 evidence reconciliation
→ 5.3 facts/calibration → 5.4 agent proof → 5.5 operational re-measurement`

- Sprint 5.0 gates the live-tenant sprints: no proof run against a real tenant starts
  before every writer default and documented output path is confirmed ignored.
- Sprints 5.3 limit verification may begin while 5.2 is in progress, but scoring
  calibration waits for honest coverage.
- Sprint 5.4 implementation is conditional on its API proof; a failed proof produces an
  explicit limitation, not a substitute design.
- Sprint 5.5 schedule-contract work can begin early, but its release gate waits for the
  preceding evidence and scoring gates.
- Ruleset-incompatible runs are not plotted as improvement/regression. They require a
  new baseline or an explicit migration approved by `@scorer`.

## Risks Across the Phase

| Risk | Mitigation / release consequence |
|------|----------------------------------|
| Metadata is absent, preview-only, or SKU-specific | Prove first; classify honestly; keep affected rules `NOT_EVALUATED`; do not close the relevant gate. |
| One-tenant observations are over-generalised | Record tenant/SKU bounds and require target-environment validation before a complete-assessment claim. |
| More fields increase apparent score | Review confidence and outcomes separately; collection changes do not justify threshold changes. |
| Calibration sample contains customer data | De-identify, retain outside git, and obtain Security approval before use. |
| Scheduler cannot be represented portably | Document the environment-owned deployment step and validate it live; do not claim repository-provisioned scheduling. |
| Ruleset changes break trend comparability | Start a new baseline or use an explicit compatible migration; never silently join versions. |
| Documentation drifts from implementation | Run the documentation gate before and after each increment; bounded claims block release when evidence is missing. |
| Documentation, help text, or a flag default creates privacy exposure without any change to collection code | The 2026-09-23 audit exposed evidence through a documented example path, not through a collector. Treat docs, CLI help, and output defaults as part of the privacy surface: every writer and output flag is ignored at any supplied value, no example steers output to a trackable location, and the pre-push identifier scan runs on documentation-only changes too. |
| Unowned documentation carries unaccountable privacy claims | `scripts/check_agent_ownership.py` audits only `fabric_iq/` modules, so `docs/IDENTITY_AND_RETENTION.md`, `docs/INSTALL.md`, `docs/SELF_ASSESSMENT.md`, and `fabric/README.md` have no owner — the structural cause of the stale-terminology finding. Sprint 5.0 assigns owners and extends the audit; until criterion 10 is met, no release gate may rest on a claim made only in those files. |
| Data already pushed cannot be un-ignored | Hardened ignore rules protect the future only. A pushed identifier requires an authorised human decision on history; record it as open rather than describing the repository as clean. |

## Explicitly Out of Scope

- Writing to or automatically fixing an assessed tenant.
- Treating `NOT_EVALUATED` as a low score, failure, or pass.
- Changing scoring to conceal collection blind spots.
- Authoring business evaluation questions, agents, prompts, or AI instructions.
- Guaranteeing all Fabric SKUs or preview surfaces from one tenant proof.
- Tenant-wide distributed quota coordination or concurrent Scanner execution unless a
  later proof shows a need and a safe, standard-library design.
- Cross-ruleset trend claims without an approved compatibility migration.
- Committing tenant-derived evidence at **any** output path, default or user-supplied:
  live payloads, transcripts, inventories, checkpoints, scores, findings, generated
  marts or reports, tenant and workspace identifiers, UPNs, emails, or credentials.
  `artifacts/` is one conventional sink, not the boundary.
- Shipping a writer, CLI output flag, documented example, or help text that steers
  evidence to a location git tracks by default.
- Rewriting pushed git history, or disposing of locally retained tenant evidence,
  without an explicit authorised human decision.

## Per-Change Quality Gate

```powershell
python assess.py --list-rules
python scripts/build_rules_doc.py --check
python scripts/check_agent_ownership.py
python -m unittest tests.test_docs
python -m unittest tests.test_self_assessment
python -m unittest discover -s tests -t .
```

In addition, verify internal links and compare documented rule/test counts with command
output.

Any change that adds or moves an output path — a writer, a CLI output flag, or a
documented example command — also runs the evidence-sink and provenance check:

```powershell
git status --short
git check-ignore -v artifacts/run_assessment.json powerbi_report/Mart_Object.csv `
                    lakehouse/gold.jsonl artifacts/checkpoint.json
git --no-pager grep -nIE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' -- .
git --no-pager grep -nIE '[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}' -- .
```

Every path passed to `git check-ignore -v` must resolve to a rule, including the flag's
documented default value. Every grep hit must be a synthetic address such as
`person@example.invalid` or a zero/placeholder GUID; any other hit blocks the push until
`@security` classifies it. These scans are heuristics — they supplement the mandatory
pre-push privacy audit and never replace it.

A live-tenant or schedule claim requires external evidence and cannot be closed by unit
tests alone. Before any push, run the mandatory privacy/provenance audit; this roadmap
update itself is not a request to commit or push.
