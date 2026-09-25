# Roadmap — IsFabricReadyForIQ

Owner: **@roadmap-planner**. This document is authoritative for scope and release gates.

Last evidence review: **2026-09-25** against ruleset `2026.09.2`.

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
- The tool is fully usable without the agent Skill. The CLI and the human documentation
  stand alone; agent-facing files route to them and are never load-bearing. Anything an
  operator must know to act on a verdict lives in human documentation, and any engine
  value an AI-facing file restates is held to the constant by an executable check.

## Architecture Principle: Fabric Is the Production Target

Production execution, storage, and consumption for this project happen **inside
Fabric**, not on a laptop: Notebook → `FabricIQReadiness` Lakehouse (Bronze/Silver/Gold
via OneLake) → Direct Lake semantic model → report. This is already implemented, not
aspirational. `fabric_iq/deployment.py`'s `build_notebook_content` binds the deployed
`Fabric_IQ_Readiness_Assessment` Notebook to that Lakehouse through the
`dependencies.lakehouse` metadata block — without which the Notebook has no
`/lakehouse/default` mount and every path in it would fail at runtime — and
`fabric_iq/lakehouse.py`'s `LakehouseWriter` documents its own `root` as "a local folder
during development and a OneLake `Files/` path when executed from a Fabric notebook."

Local CLI runs against `examples/sample_tenant`, a local `artifacts/` output, or an
external evidence folder (for example, a path outside the repository used to hold
findings from an interactive exploratory session) are development/test conveniences
only. They exercise the same engine, but they are **not** a production run: no such run
may be described, cited, or accepted as production evidence, and none satisfies a
release gate that requires Fabric execution. A live proof of this pipeline counts only
when the Notebook executes inside the workspace under its own configured identity,
writes Gold marts to OneLake, and the Direct Lake model/report refresh from there — not
when evidence is pulled to a local machine through an interactive session.

This does not relax the Sprint 5.1 identity/scope prerequisite: the Notebook's own
read-only service principal still needs prior `@security` review before any real
collection, whether that collection happens through the Notebook or through an
interactive session.

## Evidence-Based Development State

The status below reflects executable repository evidence and bounded live-validation
records, not earlier roadmap labels.

| Area | Delivered evidence | Remaining gap | Status |
|------|--------------------|---------------|--------|
| Contract and offline pipeline | Scoring, rollups, remediation, preceptorship, medallion output, and CLI run end to end on `examples/sample_tenant`; scoring regressions cover caps, coverage, and independent results. | None for the synthetic/offline scope. | ✅ Delivered |
| Rule catalogue | `python assess.py --list-rules` runs clean; the ruleset, rule total, and per-type breakdown are recorded once in **Verified Repository Baseline** below. | Encoded product limits do not yet all carry a source and exact re-verification date. | 🟡 Partially evidenced |
| Live collection | `FabricHttpTransport`, Scanner `getInfo`, pagination, bounded 429 retry, Bronze evidence, checkpoint resume, and read-only request validation are implemented and tested. Recorded live runs validate the transport, Scanner normalisation, capacity join, and both pipeline gate branches. A 2026-09-24 exploratory read added a redacted field-availability record over two non-Scanner surfaces ([`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md)). | Complete field coverage is not validated. Prep-for-AI, AI instructions, verified answers, Data Agent definition/source fields, relationships, and some capacity signals remain unconfirmed or unavailable. Live Scanner evidence evaluates roughly 8 of 17 semantic-model rules. The 2026-09-24 record is **provisional**: it ran under a delegated over-privileged identity without prior scope approval, so it is not Sprint 5.1 gate evidence, and it showed the two surfaces it exercised returning **disjoint** workspace sets. | 🟡 Partial field coverage |
| Degradation under real evidence | The 2026-09-24 exploratory read scored a real, largely unobservable estate and produced the contracted outcome: 100% of scorecards `NOT_EVALUATED`, tenant coverage 0.10 / confidence 0.00, zero blocking findings, preceptorship `escalated` at 2.34★, CLI exit 3 under `--fail-on-review`. The tool refused to publish a verdict it could not defend. | This validates **degradation**, not collection coverage, and it is one tenant on one day through one identity. It moves no gate: no rule gained evidence and no availability classification is confirmed by it. | ✅ Contract held under live evidence |
| Scale and incrementality | Synthetic tests cover proactive per-process quota handling, interrupted-run resume, and honest partial coverage for 500 workspaces. | Scans are sequential; quota state is not tenant-wide; `modified_since_days` is not wired to incremental scanning. These are explicit limitations, not delivered capabilities. | 🟡 Bounded |
| Scoring and backlog | Explainable scorecards, CSV/JSON backlog, owner role, effort, trend classification, and remediation burn-down are implemented and tested. Product-limit sourcing and dating closed 2026-09-24 (`docs/KNOWN_LIMITATIONS.md` §8). | Weights and thresholds have not been calibrated against independently labelled real objects. | 🟡 Calibration open |
| Data Agent readiness | Fifteen static rules consume supplied evidence and degrade missing inputs to `NOT_EVALUATED`. | No harness executes a corpus against a real agent; behavioural accuracy, refusal, latency, and persona isolation are therefore not measured by this repository. | 🟡 Static only |
| Fabric publication | Notebook, Data Pipeline, Lakehouse, Gold Delta marts, Direct Lake semantic model/report, run summary, trends, burn-down, and CI exit gates exist. The model/report synthetic self-assessment gate is executable. A versioned schedule contract covering cadence, `concurrency: 1` overlap prevention, identity requirement, schedule-run housekeeping, failure notification, and rerun procedure is documented in `fabric/README.md` and `docs/INSTALL.md`; the Bronze/Silver/Gold retention contract is documented as 90/180/730 days in `fabric_iq/lakehouse.py` and `docs/IDENTITY_AND_RETENTION.md`, with a durable per-run manifest and a tested, explicitly invoked `LakehouseRetentionPruner.prune()` mechanism now implemented. | No actual unattended/scheduled run has been evidenced. Retention enforcement is a tested library mechanism only: no live deployment schedule invokes the pruner yet. “Scheduled” and “unattended” are not yet delivered claims. | 🟡 Schedulable |
| Re-measurement | Comparable-run trends, automatic baseline selection, coverage-loss classification, and remediation-state comparison are implemented. | A repeatable operational cadence, ruleset-compatible baseline policy, and recorded remediation/re-measure cycle are not yet proven end to end. | 🟡 Mechanism delivered |
| Consumption-surface coverage | One of the three Sprint 6.1 rule families has shipped: `SEM-018` and `REP-011` assess **endorsement** (both MINOR), fed by Scanner `endorsementDetails` which the collector now carries with absence treated as unknown. A Sprint 6.1 availability record classifies all three Microsoft 365 gating settings as currently unevaluable. A non-normative `@scorer` design note for Sprint 6.2 exists in `docs/SCORING.md`. | A 2026-09-24 documentation review found the **GA** Microsoft 365 consumption surface (Cowork, Copilot Chat) assessed by no rule, the **preview** Fabric IQ ontology item enumerated by the collector but judged by nothing, and one headline verdict standing for four different reachability paths. The **tenant-setting** family is unevaluable at source; the **type-reachability** family is **blocked on the Sprint 6.2 decision** — today's engine has no rule outcome that states unreachability without moving a score or coverage. No Phase 6 release-gate criterion is met. | 🟥 Open, partially started |
| Scope currency | All three kinds of decay now have a named watcher. The third gained one in this session: [`SCOPE_LEDGER.md`](SCOPE_LEDGER.md) (Sprint 7.1) gives every one of the 13 elements of `WORKSPACE_ITEM_KEYS` exactly one signed disposition — 3 assessed, 4 open, 5 deliberately excluded with a reason, an owning agent and a review-by date, 1 untriaged — and `scripts/check_scope_ledger.py` (Sprint 7.2) reconciles ledger against code offline, on all four CI legs and in the per-change gate, negative-tested three ways. Product facts stay watched by `docs/KNOWN_LIMITATIONS.md` §8 and API surfaces by [`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md). | The new watcher is **one source wide**. `TENANT_SETTING_MAP`, `ObjectType`, consumption surfaces and agent kinds are not reconciled by it (Sprints 7.3/7.4), and no self-reconciliation reaches shape the repository has never named — the Cowork class of miss, covered only by 7.3's dated review obligation, which does not exist yet. One element remains **untriaged** (row 13, `GraphModel`, held on Q3 to `@collector`), so criterion 1 is open. Of seven Phase 7 release criteria, **one** (criterion 2) is met. Reading a green scope gate as "the catalogue is current" is the specific misreading this row exists to prevent. | 🟡 Started, one criterion met |

### Verified Repository Baseline

At this review the documentation gate reported:

- ruleset `2026.09.2`, **67 rules** across five object types — tenant 12, workspace 11,
  semantic model 18, report 11, Data Agent 15;
- **573 passing** unit tests plus **2 skipped by design on Windows**, so the runner
  reports `Ran 575 ... OK (skipped=2)`. **Read the convention before quoting it:** the
  bolded figure in this section is always the number that **passed**, never the number
  that **ran**. 573 ≠ 575, and citing the "Ran" figure as "passing tests" has already
  been corrected twice in this section. If you are copying a number out of a `unittest`
  run, subtract the skips first. The two skips are:
  `tests.test_evidence_sinks` cannot create a filename containing a control character
  on NTFS, so the `-z` quoting proof skips rather than passing vacuously; and
  `tests.test_lakehouse`'s `dir_fd`-anchored deletion proof skips because Windows
  supports neither `os.O_DIRECTORY` nor `dir_fd` for `os.stat`/`os.unlink` — that test
  runs and passes on Linux/macOS, where the anchored delete is live, so on those
  platforms the same revision reports 575 passing and 0 skipped;

- clean generated rule documentation, internal links, and synthetic self-assessment gate;
- `python scripts/check_agent_ownership.py` exit 0 — **28** modules under `fabric_iq/`
  and `scripts/` claimed exactly once, and the **8** documents and skills asserting a
  privacy, identity, retention or collection-capability claim — or read by a model as
  instruction — each claimed by exactly one agent through an explicit `REQUIRED_DOCS`
  map. The seventh is [`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md), owned by
  `@collector`; the eighth is [`SCOPE_LEDGER.md`](SCOPE_LEDGER.md), owned by `@readme`,
  which entered the map with Sprint 7.1;
- `python scripts/check_scope_ledger.py` exit 0 — **1 declared shape source**
  (`WORKSPACE_ITEM_KEYS`, 13 elements) reconciled against **13 ledger rows**, the count
  the document states. The disposition mix at this revision is **3 assessed / 4 open /
  5 deliberately excluded / 1 untriaged**, measured by reading the ledger rows directly
  rather than carried from any agent's report. It moved this session — an earlier
  measurement recorded four exclusions — because `@dataagent`'s 2026-09-25 triage ruled
  `Lakehouse` and `KQLDatabase` **open** (in scope as subjects) and excluded `Eventhouse`
  as a duplicate subject at the wrong grain, which is row 12 and the fifth dated
  exclusion. **All five exclusions carry `2026-12-24`**; the comparison is
  `review_by < as_of`, so the gate passes on 2026-12-24 and fails on 2026-12-25 —
  confirmed by running `audit()` at both dates (0 expiries, then 5). Rows 6–9 are
  `@readme`'s to re-date, row 12 is `@dataagent`'s. **The untriaged row is not a low
  score and not a failure**: it is row 13 (`GraphModel`), held on Q3 to `@collector`, and
  it is the single thing keeping Phase 7 criterion 1 open. One source is the whole of the
  gate's reach at this revision; see **Per-Change Quality Gate** for what it therefore
  does not watch;
- `python scripts/check_evidence_sinks.py` exit 0 — **75 writer destinations** and
  documented output examples each resolve to a committed `.gitignore` rule, all **109
  tracked files** remain trackable (none shadowed by a broad pattern such as `*.jsonl`
  or `Mart*.csv`), and no tracked file carries a real tenant identifier, UPN, email, or
  non-placeholder GUID. Both figures move with the working tree and are properties of the
  current revision, not stable totals. The destination figure moved twice since the
  previous review, and both movements are worth understanding before anyone treats it as
  a metric: it fell from **61** to **60** when a documented `--checkpoint` example was
  replaced with an out-of-repository placeholder, then rose to **62** because this
  roadmap's own baseline and exploratory-read entries name two example output paths
  (`--out artifacts/live`, `--checkpoint artifacts/live-checkpoint.json`), which
  registers them with the gate — both resolve to the ignored `artifacts/` rule. Prose
  that names an output path *is* an output example; that is the design, and it is the
  lesson of the 2026-09-23 exposure, which arrived through a documented path and not
    through a collector. The API reality matrix has since been committed, and Sprints 7.1
    and 7.2 added four more tracked files (`docs/SCOPE_LEDGER.md`,
    `scripts/check_scope_ledger.py` and its two test modules), which is why the
    tracked-file figure now reads 109; the destination figure did not move with any of
    them, because the `artifacts/live` example already registered here is the only output
    path they name.

  All figures above were re-measured against the working tree being committed on
  **2026-09-25** by running the five gate commands directly, rather than carried forward
  from any agent's report. **Re-measured again later on 2026-09-25, for this roadmap
  correction: every one of them held.** 573 passing / 2 skipped / `Ran 575`, 28 modules,
  8 required documents, 109 tracked files, 75 writer destinations, ruleset `2026.09.2`
  with 67 rules, and 1 declared source / 13 elements / 13 rows. **Nothing moved, and
  that is the result, not the absence of one** — this correction changed only
  `docs/ROADMAP.md`, which is neither a module, a required document, a writer
  destination nor a rule, so a moved figure would have been the finding. The one
  measurement that *did* move is not a gate figure at all: the ledger's disposition mix,
  recorded above. Since the earlier 2026-09-25 measurement described below, four
  moved, and all four move for the same reason — Sprints 7.1 and 7.2 landed: the test count
  (530 → **573 passing**, `Ran 575`), modules (27 → **28**, `scripts/check_scope_ledger.py`),
  required documents (7 → **8**, `docs/SCOPE_LEDGER.md`) and tracked files
  (105 → **109**). **The ruleset token and rule total (`2026.09.2`/67) and writer
  destinations (75) did not move**, and were re-run rather than assumed. A figure that is
  expected to have drifted and has not is still a measurement; record it as unchanged
  instead of quietly restating it. Earlier in the same session the ruleset token and rule
  total had moved from the 2026-09-24 review (`2026.09.1`/65 → `2026.09.2`/67, and the
  per-type breakdown with them) and the test count from 486 → 530.

  The test figure has now moved **three times within this session**, which is the failure
  mode this section exists to catch: it was first measured at 520 passing, rose to 530
  when `@tester` added ten cases to `tests/test_skill_drift.py` (6 → 16 test methods),
  and rose again to 573 when Sprints 7.1 and 7.2 added `tests/test_scope_ledger.py` and
  `tests/test_scope_ledger_gate.py`. 573 is the figure for the tree being committed,
  measured after those changes landed. **The lesson is procedural, not
  arithmetic:** a baseline measured before concurrent work lands is stale on arrival, so
  re-measure at the commit boundary rather than at the start of the edit.

#### Ruleset ledger note — `2026.09.1` is `AMBIGUOUS_FINGERPRINT`, not a hash

`@scorer` bound the ruleset token to a catalogue fingerprint and incremented to
`2026.09.2`. The ledger entry for the **previous** token carries
`AMBIGUOUS_FINGERPRINT` rather than a hash, because `2026.09.1` was stamped on four
different catalogues (61, 63, 65 and 67 rules) while nothing tied the token to the
catalogue it described. The consequence is stronger than "old runs are not comparable
with new ones": **runs stamped `2026.09.1` are not comparable with each other**, because
the token never identified one ruleset. Two further consequences follow, and both are
intended:

- The first run at `2026.09.2` has an **empty trend section by design**. There is no
  compatible baseline to select, and manufacturing one by joining across the boundary is
  exactly the silent version join this roadmap's sequencing policy forbids.
- Recording the ambiguity as a ledger value is the honest form. Back-filling a
  fingerprint for `2026.09.1` would re-label evidence that already exists in someone's
  Lakehouse.

This roadmap's sequencing policy requires an explicit `@scorer` approval for any ruleset
migration. **`@scorer` has approved this one**, which satisfies that requirement; it is
recorded here so the approval is traceable to the policy that demanded it.

Both checks were shown to be non-vacuous by deliberate negative tests on 2026-09-23:
removing the `powerbi_report/` ignore rule, planting a UPN in a tracked file, and
removing a documentation ownership claim each fail with exit 1 and name the unprotected
path, the host and address, or the required owner. A gate that cannot fail is not a gate
— and, as Sprint 5.0.1 found, neither is one that cannot see the file it is meant to
cover.

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
classification, with unsupported evidence producing `NOT_EVALUATED`. The 2026-09-24
exploratory read drafted such a classification for two surfaces but under an identity the
gate does not accept, so the gate is unmoved.

## Phase 2 — Static Readiness Scoring 🟡

The engine, rule catalogue, actionable backlog, and output formats are delivered.
Product-limit sourcing closed 2026-09-24 (`docs/KNOWN_LIMITATIONS.md` §8); the
calibration mechanism landed 2026-09-24 (`fabric_iq/calibration.py`), but practitioner
calibration itself remains open under Sprint 5.3 — no labels have been collected.

**Exit gate.** Partially open: every encoded limit now has a public source and exact
verification date (closed 2026-09-24), and the blinded worksheet, agreement analysis and
disagreement enumeration now exist and are tested (2026-09-24). Calibration
disagreements recorded without tenant-specific tuning is not yet done — the instrument
exists, the measurement has not been taken — and the gate does not close until that half
lands too.

## Phase 3 — Agentic Readiness 🟡

Fifteen static Data Agent rules consume supplied metrics. No repository harness executes
a corpus against a real agent, so behavioural readiness is not yet measured.

**Exit gate.** Open: the execution surface is proved before implementation and a
supplied corpus produces reproducible per-persona metrics, or unavailable evidence stays
explicitly `NOT_EVALUATED`.

## Phase 4 — Industrialisation 🟡

Pipeline execution, Delta persistence, the semantic model/report, trends, remediation
burn-down, self-assessment, and CI gates are delivered. Schedule contract v1 is now
versioned and documented in `fabric/README.md` and `docs/INSTALL.md`, including
cadence, `concurrency: 1` overlap prevention, identity requirement, schedule-run
housekeeping, failure notification, and rerun procedure. The pipeline remains only
schedulable: no actual unattended/scheduled run or two-run re-measurement cycle has
been proven. The 90/180/730-day Lakehouse retention mechanism now has durable
run manifests and tested explicit pruning, but no live deployment schedule invokes it yet.

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
metadata remain unconfirmed; the repository also has a Data Pipeline with a versioned
schedule contract and a tested Lakehouse retention-pruning mechanism, but no proven
unattended/scheduled run and no live deployment schedule invoking that pruner. Since
2026-09-24 a second, sharper anchor exists:
[`docs/API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md) states field by field what two live
read surfaces did and did not return — provisionally, under an identity Sprint 5.1 does
not accept.

**Falsifiable hypothesis.** The required read-only metadata is either available from
documented tenant surfaces with stable field shapes, or can be classified explicitly as
unavailable so affected rules remain `NOT_EVALUATED`.

**Cheap check.** Before changing a collector or rule, issue the minimum read-only calls
for one authorised workspace and record a redacted field matrix:
`available / partial / absent / permission-blocked / preview-only`. No customer payload
is committed. The 2026-09-24 read is that cheap check performed once; what it lacks is
the approved scoped identity that would make its rows citable.

**Exit gate.** All eleven criteria in **Release Gate for Phase 5** are met; in particular,
unsupported evidence remains `NOT_EVALUATED`, no output path can place tenant-derived
evidence under version control, and two compatible unattended runs prove the complete
re-measurement loop.

### Sprint 5.0 — Evidence-Sink and Provenance Hygiene ✅ Delivered 2026-09-23

The one retention decision this sprint left open was resolved by the user on 2026-09-24;
§6 records the disposition. Nothing in this sprint remains open.

1. **Outcome** — Delivered. No tenant-derived evidence can reach version control through
   any documented command, writer default, or CLI output flag, and every file that makes
   a privacy, identity, or retention claim has a named accountable owner. Both
   properties are now asserted by executable checks that run in CI, not by convention.
2. **Originating evidence** — A `@security` audit on 2026-09-23 found that the documented
   `assess.py --inventory <inv> --powerbi ./powerbi_report` wrote object and workspace
   names, scores, and findings into `powerbi_report/`, which was not git-ignored, so a
   `git add .` after a live run would have committed tenant-derived evidence. The same
   audit found `--out`, `--lakehouse`, and `--checkpoint` safe only at their documented
   default values; `--checkpoint` persisting `tenant_id` and raw Bronze payloads
   including `identity`; `.gitignore` ignoring `*.ndjson` while the writer emits
   `.jsonl`; a real tenant admin UPN committed to `CHANGELOG.md` and pushed; and
   `scripts/check_agent_ownership.py` auditing only modules under `fabric_iq/`, so
   [`IDENTITY_AND_RETENTION.md`](IDENTITY_AND_RETENTION.md), [`INSTALL.md`](INSTALL.md),
   [`SELF_ASSESSMENT.md`](SELF_ASSESSMENT.md), and `fabric/README.md` were claimed by no
   agent.
3. **Delivered slices** —
   - (a) Ignore rules, CLI help warnings, and forward redaction fixed and verified.
   - (b) `scripts/check_evidence_sinks.py` (`@tester`, claimed in `tester.agent.md`)
     makes release-gate criterion 9 executable rather than a manual command sequence: it
     asserts that every writer destination and documented output example resolves to a
     committed `.gitignore` rule, that every tracked file remains trackable, and that no
     tracked file contains a real tenant identifier, UPN, email, or non-placeholder GUID.
     The counts it reports move with the repository and are recorded only in
     **Verified Repository Baseline** above, so they cannot go stale here.
   - (c) `scripts/check_agent_ownership.py` extended with an explicit `REQUIRED_DOCS`
     map, making criterion 10 executable: `docs/INSTALL.md` and `fabric/README.md` →
     `@orchestrator`; `docs/SELF_ASSESSMENT.md` → `@preceptor`;
     `docs/IDENTITY_AND_RETENTION.md` → `@readme`. `@security` still owns no file by
     design, so each privacy claim is owned by the agent accountable for the surface it
     describes. The set is explicit, not inferred — guessing which file makes a privacy
     claim is how such a check silently stops covering one. It held four entries at
     closure; Sprint 5.0.1 grew it to six and fixed the parser defect that let a
     dot-directory entry match nothing; the 2026-09-24 exploratory read added the
     seventh, `docs/API_REALITY_MATRIX.md` under `@collector`, because a
     collection-capability claim is owned on the same terms as a privacy one.
   - (d) `docs/IDENTITY_AND_RETENTION.md` reconciled with the code: all four sinks
     documented, `.jsonl` corrected, and an unsourced "30–90 day" retention figure
     removed rather than rationalised after the fact.
   - (e) CI runs the evidence-sink gate as its own named step in
     `.github/workflows/ci.yml`, alongside the ownership and rule-documentation steps.
   - (f) The pushed-history decision is **resolved**: the user deleted and recreated the
     public repository, so the orphaned commit carrying the real tenant admin UPN now
     returns 404 and is permanently destroyed. The republished history is 21 commits with
     0 occurrences. This is a stronger outcome than a force-push, which leaves orphaned
     objects served by SHA until GitHub garbage-collects them.
4. **Dependencies** — `@security` owned the privacy verdict, scopes, and retention;
   `@orchestrator` owned CLI help text and output-flag defaults; `@tester` owned the
   executable ownership and evidence-sink checks; `@readme` owned documentation ownership
   declarations; the history decision was the user's. Standing constraint for every later
   sprint: no writer may be introduced whose default or documented path is trackable, and
   any new document asserting a privacy, identity, or retention claim must be added to
   `REQUIRED_DOCS` in the same change.
5. **Validation performed** — `python scripts/check_evidence_sinks.py` exit 0; `python
   scripts/check_agent_ownership.py` exit 0 (22 modules, 4 required documents at
   closure); the full suite green at **295 tests**, up from 256; `python
   scripts/build_rules_doc.py --check` clean at ruleset `2026.09.1`, 65 rules.
   Those are point-in-time closure figures. The current revision's counts live in
   **Verified Repository Baseline**, which is the single place this roadmap keeps live
   counts.
   Three independent negative tests proved the gates are not vacuous: removing the
   `powerbi_report/` ignore rule fails with exit 1 naming the unprotected paths; planting
   a UPN in a tracked file fails naming the host and address; removing a documentation
   ownership claim fails naming the required owner.
6. **Closed since, and non-goals** — One item remains a standing caveat; the other is now
   resolved:
   - **Resolved 2026-09-24 — local evidence disposition.** The user decided the retention
     question this sprint could not settle: `artifacts/checkpoint.json` from the
     2026-09-21 live run is **destroyed**, together with five 2026-09-21 live run outputs
     carrying real UPNs, three readiness reports rendering real workspace names, and two
     duplicate run triplets. `artifacts/` in the checkout now holds synthetic output
     only. The live evidence that is still needed was moved to a store **outside the
     repository and outside any synced folder**, with an expiry of **2026-10-08**.
     `@security`'s standing rule is adopted from this point: **a proof run receives its
     expiry at authorisation, not afterwards.** Retrofitting an expiry onto evidence
     that already exists is how a dataset quietly becomes permanent.
   - The checks are heuristics. They reduce the chance of an exposure reaching a push;
     they never replace the mandatory pre-push privacy audit, and no release gate may
     cite them as proof that a repository is clean.

   Non-goals unchanged: this sprint did not add redaction to collected evidence, did not
   weaken checkpoint resume, and makes no claim about tenant content that was never in
   git.
7. **Commit boundary** — Ignore rules, CLI help text, and their verification belonged
   with the orchestrator/security change. `scripts/check_evidence_sinks.py`, the
   `REQUIRED_DOCS` extension, `tests/test_evidence_sinks.py`, the CI step, and the four
   documentation ownership declarations formed the separate `@tester`/`@readme` boundary.
   The `artifacts/` disposition produces no commit, and the history resolution produced
   none either — it was a repository-level user action.

### Sprint 5.0.1 — Standalone Operability and Skill Claim Integrity ✅ Delivered 2026-09-23

Numbered `5.0.1`, not `5.1a` or a new sprint of its own rank, on purpose. This is
assurance and hygiene over surfaces Sprint 5.0 created — it adds no assessment
capability, no rule, no collected field, and no scoring behaviour. It is a follow-on to
5.0 because it repairs and extends the very ownership gate 5.0 delivered. Sprint 5.1
remains the next actionable sprint and its rank is unchanged.

1. **Outcome** — Delivered. The tool is usable without the agent Skill: the CLI output
   and the human documentation carry the interpretation knowledge, and the Skill routes
   to them rather than being the only place they exist. Where the Skill does restate an
   engine value, that value is now held to the constant by an executable check and the
   file has a named owner. **The Skill is never load-bearing.**
2. **Originating evidence** — Three separate findings, all against the user requirement
   that the tool stand alone:
   - `.github/skills/fabric-iq-readiness/SKILL.md` was claimed by no agent and checked
     only for existence by `tests/test_docs.py`, while restating engine constants as
     hand-written prose. Unlike `docs/RULES.md` it is not generated, so a changed
     constant would have left a model quoting last release's number as authoritative
     instruction at prompt time.
   - The operational interpretation knowledge — blocking-first reading order, the
     `NOT_EVALUATED` do-not-re-score rule, the triage table, and the non-obvious domain
     rules — existed **only** in AI-facing files. A human running `assess.py` with no
     agent present could read the numbers and not know which to act on first.
   - The claim parser in `scripts/check_agent_ownership.py` could not begin a path with
     a dot, so a `.github/...` entry matched nothing and the Skill would have been read
     as permanently unclaimed. The gate was **failing open** — the most expensive
     failure mode a gate has, because it reports success.
3. **Delivered slices** —
   - (a) `.github/skills/fabric-iq-readiness/SKILL.md` added to `REQUIRED_DOCS` under
     `@readme`; `docs/INTERPRETING_RESULTS.md` added under `@readme` as well. The map now
     covers instruction-bearing files, not only
     privacy/identity/retention ones.
   - (b) `tests/test_skill_drift.py` (`@tester`) asserts that every value the Skill
     states equals the imported engine constant. It matches on the **claim sentence**
     with the value captured, not on a bare substring, and asserts over *every*
     occurrence — so a contradictory second statement elsewhere in the file cannot pass.
     Ten claim sentences cover nine engine constants (`MAX_DATA_SOURCES`,
     `MAX_RESULT_ROWS`, `MAX_RESULT_COLUMNS`, `DESCRIPTION_BUDGET`,
     `AI_INSTRUCTIONS_MAX`, `MIN_ACCURACY`, `MIN_CRITICAL_ACCURACY`,
     `MIN_COVERAGE_TO_PUBLISH`, and `SEVERITY_SCORE_CAP` for both the blocking and major
     caps). The module also self-tests the comparison against synthetic stale,
     contradictory, and line-wrapped text, so the drift check is not decoration.
   - (c) The claim-parser regex now permits a leading dot, with two regression tests
     (`test_a_dot_directory_path_is_recognised_as_a_claim` and
     `test_a_dot_directory_style_claim_covers_the_files_inside_it`) pinning the
     behaviour. The fix is worth more than the entry it enabled: it closed a gate that
     reported clean while covering nothing under a dot-directory.
   - (d) [`docs/INTERPRETING_RESULTS.md`](INTERPRETING_RESULTS.md) now carries the
     interpretation knowledge for humans, `README.md` links it, and the Skill routes to
     it. Direction matters: human documentation is the source and the AI-facing file is
     the pointer, never the reverse.
   - (e) The console and HTML reports gained a `HOW TO READ THIS` orientation block with
     live blocking and `NOT_EVALUATED` counts and a pointer to the guide, so the reading
     order travels with the output rather than depending on the reader having the docs
     open. Tests assert that it precedes the numbers it explains, stays short, reports a
     clean run without inventing walls, is HTML-escaped, and **does not move a single
     scored value** — presentation must not become a third result.
   - (f) `tests/test_standalone_guidance.py` (`@tester`) makes the non-dependence
     property itself executable, which is what turns this sprint from an intention into
     a gate. It asserts that the guide path the reports hardcode resolves to a real,
     non-stub, repo-relative human document that somebody owns and that is not a Skill;
     that `@readme` has actually claimed it and the ownership audit reports it; and that
     every operational concept is explained in the **human** corpus with AI-facing files
     explicitly excluded from that corpus. It is negative-tested from both directions:
     an empty corpus, unrelated prose, scattered keywords, a deleted guide, and a single
     stripped concept each fail, while a reasonable rewording still passes — so the gate
     tracks meaning rather than an exact phrase, and cannot be satisfied by a stray
     sentence.
4. **Dependencies** — `@readme` owned the Skill reconciliation, the human guide, and the
   ownership declarations; `@tester` owned the drift check, the parser regression tests,
   the orientation assertions, and the standalone-guidance gate; `@lakehouse` owned the
   report orientation block.
   Standing constraint for every later sprint: any new AI-facing file that restates an
   engine constant must arrive with an owner in `REQUIRED_DOCS` and a drift assertion in
   the same change, and no operator guidance may live only in an agent-facing file.
5. **Validation performed at closure** — `python -m unittest discover -s tests -t .` →
   **345** tests OK; `python scripts/check_agent_ownership.py` exit 0 (22 modules, 6
   required documents and skills); `python scripts/check_evidence_sinks.py` exit 0 (61
   writer destinations, 99 tracked files); `python scripts/build_rules_doc.py --check`
   clean at ruleset `2026.09.1`, 65 rules. Those are point-in-time closure figures,
   taken while this sprint's own new files were still untracked — which is why the
   tracked-file count read 99 here and reads higher once the work is staged. **Verified
   Repository Baseline** holds the current counts. New release-gate criterion **11**
   records the non-dependence property and is met at this revision.
6. **Still open, and non-goals** — Nothing in this sprint is left open. What it does
   **not** claim matters more than what it does: the gates assert that the Skill cannot
   silently contradict the engine and cannot be the only home of operator guidance —
   they do not assert that the Skill, the guide, or the orientation block is *good*.
   Concept coverage is a presence-and-meaning check over human documentation, not a
   readability or accuracy review; a human still owns whether the guidance is correct.
   Non-goals: this sprint added no rule, changed no score, weight, cap, threshold or
   coverage floor, collected no new field, and did not let the orientation block move a
   single scored value.
7. **Commit boundary** — Four boundaries. The Skill ownership entry, the parser fix and
   its regression tests, and `tests/test_skill_drift.py` form the assurance boundary.
   The human guide, its README link, and the Skill's routing change form the
   documentation boundary. The report orientation block and its assertions form the
   reporting boundary. `tests/test_standalone_guidance.py` is the fourth and must stay
   separate from the three it gates — a gate reviewed in the same commit as the thing it
   gates is reviewed once, not twice.

### Exploratory Read — 2026-09-24 — Live API Availability Observation

**Not a sprint, and explicitly not Sprint 5.1 gate evidence.** It is recorded here
because it produced durable, redacted API-availability knowledge that constrains later
design, and because an unrecorded live read is the kind of thing that gets re-quoted
later as something it was not.

1. **What happened** — The user authorised a read-only exploratory read of a live Fabric
   tenant through an authenticated MCP session. Two surfaces were exercised — a OneLake
   data-plane workspace listing and a Fabric catalog search — and the resulting
   field-by-field availability record is
   [`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md), owned by `@collector` and now
   enforced in `REQUIRED_DOCS`. Estate size is recorded there as ratios only; this
   roadmap does the same.
2. **Why it does not clear Sprint 5.1** — `@security` ruled that it cannot serve as gate
   evidence, on two conditions this roadmap's own Sprint 5.1 text states. First, 5.1
   requires `@security` to review scopes and retention **before** the proof; here the
   review happened afterwards. Second, 5.1 requires a **read-only service principal**;
   this ran under a **delegated interactive identity** carrying the operator's full
   privilege set, including every write that person holds. Least privilege was never
   demonstrated, so no row evidences read-only enforcement. Citing this run as the 5.1
   proof would be quoting a gate that did not run. The matrix carries the same caveat at
   its head.
3. **Findings that survive the caveat** — Field availability is a property of the
   endpoint, not of the identity's provenance, and an over-privileged identity can only
   overstate what a scoped one would read, so an `absent` row is if anything
   conservative:
   - `capacityId` returned `null` for **100% of workspaces** on the OneLake listing.
     Capacity-dependent workspace rules — including blocking ones — cannot be evaluated
     from that surface at all.
   - **The two surfaces returned disjoint workspace sets: 0% overlap by GUID and 0% by
     case-folded display name.** A collector built on either surface alone silently omits
     the other entirely. This is the finding that most constrains future collector
     design, and it is a *silent* failure mode — the omitted estate looks like an estate
     that does not exist.
   - Workspace `id` on that surface is an **opaque non-GUID string**; the GUID lives only
     in `metadata.workspaceObjectId`. A normaliser keying on `id` by convention would key
     the inventory on a mutable display name, and cross-surface joins would fail without
     raising.
   - **No Data Agent item type was exposed, and no tenant admin setting was reachable**
     on these surfaces. Neither is a negative product claim: these two endpoints were
     exercised, the Scanner, Admin, XMLA, item-definition and Activity Events APIs were
     not.
4. **What the run validated — degradation, not coverage** — Running the engine on this
   evidence produced the contracted behaviour exactly: **100% of scorecards
   `NOT_EVALUATED`**, tenant coverage `0.10` / confidence `0.00`, **zero blocking
   findings**, preceptorship **escalated at 2.34★**, CLI **exit 3** under
   `--fail-on-review`. The tool refused to publish a verdict rather than inventing one.
   That is a genuine validation of the three-result contract against a real estate and is
   worth recording as such. Read the two numbers correctly: zero blocking findings on an
   unobserved tenant is correct behaviour, not a clean bill of health — a rule that could
   not run cannot fail; and a 2.34★ escalation is the tool declining to defend a verdict
   it cannot support. Nothing here is a readiness result about the tenant.
5. **Evidence handling** — Raw payloads were written only to a git-ignored path and were
   never tracked; the evidence still needed was then moved to the out-of-repository store
   described in Sprint 5.0 §6, expiring **2026-10-08**. No workspace name, GUID, portal
   link, UPN or regional host appears anywhere in this roadmap, which
   `scripts/check_evidence_sinks.py` asserts on every change; the matrix states and owns
   the same discipline for itself.
6. **Consequences carried forward** — Sprint 5.1 stays open and its blockers are
   restated below. Sprint 5.2 inherits a **provisional shortlist to re-confirm**, not a
   confirmed field set, plus one new design constraint recorded in its own entry.

### Re-Verification Attempt — 2026-09-24 — Live Workspace Unreachable

Later the same day, this session attempted to re-probe the live "Fabric IQ Readiness"
workspace exercised by the exploratory read above, as a sanity check before further
planning. The attempt failed on every path tried. It is recorded factually, without
elaboration beyond what was actually observed, because it changes how Sprint 5.1's
evidence must be produced even though it changes nothing about the sprint's scope:

- `Fabric-MCP-onelake_list-items` against the workspace ID recorded earlier in the
  session returned `WorkspaceNotFound` (404).
- The workspace does not appear at all in a full 81-entry OneLake workspace listing by
  name.
- `Fabric-MCP-core_search-catalog` returned `403 InsufficientScopes` — the same call
  that had succeeded earlier in this same session.

Nothing beyond these three observations is claimed. In particular, this does **not**
establish *why* the workspace became unreachable (deletion, rename, a permission change,
or session/token state) — only that it did. What it does establish, consistent with the
**Architecture Principle** above: ad hoc interactive-session probing of a live tenant is
not a stable or appropriate way to validate this pipeline, and was never the target
architecture. The deployed pipeline's actual functioning must be proven by running the
`Fabric_IQ_Readiness_Assessment` Notebook inside Fabric under its own configured
identity — once Sprint 5.1's scoped-service-principal prerequisite is met — not by
further interactive-session probing from outside. This finding does not reopen, close,
or change the scope of Sprint 5.1; it reinforces why the sprint's prerequisite is a
service-principal proof rather than a repeatable interactive read.

### Sprint 5.1 — Close the API Reality Matrix (3–5 days) — 🟥 **OPEN**, next actionable sprint

**Status: not cleared.** The 2026-09-24 exploratory read did **not** satisfy this sprint,
and no later sprint may treat it as though it had. Two stated prerequisites did not
happen: `@security` did not review scopes and retention *before* the read, and the reads
were issued under a delegated interactive identity holding the operator's full write
privileges rather than a **read-only service principal**. What is still required is a
**re-run under a service principal whose scopes and evidence expiry `@security` approves
first**. Until that exists, every availability classification in the matrix is
provisional, however plausible it looks.

The same-day **Re-Verification Attempt** recorded above adds a second reason this cannot
be closed by further interactive probing: the workspace it exercised became unreachable
the same way it had been reached earlier in the session. Per the **Architecture
Principle**, the re-run this sprint requires is the `Fabric_IQ_Readiness_Assessment`
Notebook executing inside Fabric under its own configured identity — not another
interactive-session read, however it is authenticated.

**Blocked on one prerequisite that is not repository work:** an authorised test tenant
and service principal with read-only scope. Every slice below is an evidence-acquisition
slice; none of it can be simulated from fixtures, and none of it may start before
`@security` has approved the scopes and the retention of the redacted field matrix.
Sprint 5.0 has cleared the gating condition: no writer default or documented output path
is trackable, so a proof run can now be performed without risking a commit of
tenant-derived evidence.

1. **Outcome** — Every field consumed by the rule catalogue has a current,
   reproducible availability classification, including the fields still unconfirmed
   after the first live run.
2. **Current evidence** — Live evidence validates the transport, Scanner normaliser,
   capacity join, and roughly 8 of 17 semantic-model rules. The availability record is
   incomplete for Prep-for-AI, AI instructions, verified answers, Data Agent
   definition/sources, model relationships, and capacity throttling. The 2026-09-24
   exploratory read supplies a **draft** of the deliverable — a redacted, ratio-only
   field matrix over two surfaces — but not the gate: it proves nothing about least
   privilege, exercised neither the Scanner nor any Admin endpoint, and ran through an
   MCP session rather than `fabric_iq/collectors/fabric_api.py`, so it also says nothing
   about the live HTTP client. Treat it as a structured hypothesis to re-test, not as a
   partially completed sprint.
3. **Smallest slice** — `@collector` runs a one-workspace, read-only proof and prepares a
   field-to-endpoint matrix with HTTP outcome, required scope, SKU/preview qualification,
   and redacted evidence reference. `@security` reviews scopes and retention before the
   proof — and sets the evidence expiry at that authorisation, not afterwards. `@readme`
   reconciles the resulting bounded claims in README and known limitations. Sequence the
   re-run so that the highest-value unknowns come first: tenant settings and capacities
   gate six rules the exploratory read could not touch at all — TEN-001, TEN-002,
   TEN-004, TEN-006, WKS-001 and WKS-010, **all six blocking**, first verified against
   `python assess.py --list-rules` at ruleset `2026.09.1` and **re-verified at
   `2026.09.2` on 2026-09-25**: all six are still present and still blocking, so the
   ruleset increment does not change this priority. A figure re-checked and found to have
   held is still a measurement.
   **Added 2026-09-25 (Sprint 6.4's prerequisite, ranked below the six above):** the
   matrix must also answer whether **lakehouse and KQL-database table and column
   metadata** is readable by a read-only caller — under which identity, at which scope,
   and at what grain. Scope-ledger rows 10 and 11 make those artefacts assessed subjects
   in principle and record that **no exercised endpoint returns that metadata**, so
   Sprint 6.4 cannot begin until this proof answers it either way. An unreadable answer
   is a useful answer and closes 6.4 with a limitation entry; an assumed answer closes
   nothing.
   Every query the proof intends to cite must be retained; the exploratory read had to
   exclude three reported observations because no payload survived to reproduce them.
4. **Dependencies** — Authorised test tenant and service principal; `@collector` owns
   acquisition; `@security` owns least privilege and provenance; `@readme` owns the
   documentation outside this roadmap. No implementation sprint may assume a field that
   this proof does not confirm.
5. **Validation** — Focused check: rerun the proof under the approved service principal
   and reproduce each matrix classification without persisting raw payloads in git; a
   classification the scoped identity cannot reproduce is downgraded, never inherited
   from the exploratory read. Release gate: every rule input maps to a confirmed field or
   an explicit unavailable/preview classification, the identity that obtained it is
   recorded, and unconfirmed inputs still produce `NOT_EVALUATED`.
6. **Risks and non-goals** — Tenant/SKU variance may prevent a universal claim. A scoped
   service principal may read **less** than the delegated identity did, which would
   demote rows rather than confirm them; that is the expected direction and is not a
   regression. This sprint does not add endpoints, weaken rules, infer absent values,
   claim that one tenant represents all SKUs, or promote an exploratory classification by
   restating it.
7. **Commit boundary** — Collector-owned proof/fixture changes and tests form one commit;
   Security/Readme-owned scope and availability documentation form a separately reviewed
   documentation commit. No live payload or identifier is included.

### Sprint 5.2 — Reconcile Collection and Rule Coverage (1–2 weeks)

1. **Outcome** — Confirmed fields are normalized and evaluated; unavailable fields
   remain visible blind spots with correct object-level confidence.
2. **Current evidence** — The collector already degrades unreadable and absent evidence,
   while the live record shows material semantic-model evidence gaps. Existing synthetic
   tests cover quota, resume, and partial-batch coverage. **Two assumptions of this
   sprint changed on 2026-09-24** and are recorded here before any implementation starts:
   - *The confirmed field set is not confirmed.* Sprint 5.1 remains a hard prerequisite
     and is open, so what the matrix calls a confirmed set is a **provisional shortlist
     to re-confirm** under the approved scoped identity. Selecting a field family from it
     today would build normalization on a classification obtained by an identity the gate
     rejects.
   - *A single read surface cannot be assumed to enumerate the estate.* The two surfaces
     exercised returned **disjoint** workspace sets — 0% overlap on GUID and on
     case-folded display name. Object enumeration is therefore a multi-surface problem,
     not a field-family problem, and it is upstream of every rule this sprint would
     activate.
3. **Smallest slice** — Select one field family confirmed by Sprint 5.1, add its
   normalization and synthetic contract fixture, then activate only the rules that can
   consume it without inference. Repeat field family by field family; permanently
   unavailable inputs stay `NOT_EVALUATED`. Two constraints now bind that work, each
   traceable to a 2026-09-24 observation and each cheap to honour before a normalizer
   exists and expensive afterwards:
   - **Key the inventory on the workspace GUID, never on a surface's `id` field.** One
     surface returned a non-GUID name string as `id`, with the GUID carried separately.
     A normalizer keying on `id` by convention would key on a mutable display name and
     cross-surface joins would fail silently rather than raise.
   - **Union multiple surfaces on the GUID and record which surface saw each object.** A
     workspace seen by only one surface must carry reduced coverage, not an unqualified
     presence — otherwise a partial enumeration reports a complete-looking tenant, which
     converts a collection gap into a false verdict.
4. **Dependencies** — `@collector` owns transport/normalization/fixtures; `@semantic`,
   `@tenant`, or `@dataagent` owns the affected rule; `@tester` owns cross-boundary
   regressions; `@scorer` reviews any shared-model impact. Sprint 5.1 is a hard
   prerequisite and is **open**; the 2026-09-24 exploratory read does not discharge it.
5. **Validation** — Focused check: for each new field family, synthetic present, absent,
   null, forbidden, and malformed cases produce the expected evidence and rule outcome.
   Add a synthetic multi-surface case: two source surfaces with disjoint object sets
   produce one unioned inventory keyed on GUID, with per-object surface provenance and
   reduced coverage for single-surface objects. Release gate: full test suite passes; no
   missing input passes or fails; confidence falls when applicable evidence is missing;
   blocking failures still cap at 39 and revoke eligibility.
6. **Risks and non-goals** — API shapes may vary or remain preview-only. Surface
   disjointness observed in one tenant is not a general law; the mitigation — union on
   GUID and record provenance — is correct whether or not it recurs, which is why it is
   stated as a design constraint rather than as a finding to reproduce. The sprint does
   not compensate for collection gaps by changing weights, caps, thresholds, or report
   visuals, and it does not automate remediation.
7. **Commit boundary** — One confirmed field family, its normalizer, synthetic fixtures,
   owned rules, and focused tests belong together. Do not bundle unrelated rule growth
   or presentation changes.

### Sprint 5.3 — Verify Product Facts and Calibrate Verdicts (1 week plus field review)

1. **Outcome** — Encoded limits are dated facts, and any proposed scoring change is
   supported by practitioner disagreement evidence rather than intuition.
2. **Current evidence** — The catalogue and scoring engine are executable.
   `@readme` closed the product-fact-verification half 2026-09-24: all eight rows in
   `docs/KNOWN_LIMITATIONS.md` §8 now carry a public source and exact verification date,
   individually re-verified against the live Microsoft Learn / REST API reference pages
   (three sources were also corrected to the page that actually states the fact).
   `@scorer` built the calibration **mechanism** 2026-09-24 (`fabric_iq/calibration.py`,
   `assess.py --calibration`, `tests/test_calibration.py`, contract in
   `docs/SCORING.md`): blinded pseudonymised worksheet, reproducible stratified 20–30
   object draw, Krippendorff-alpha agreement reported inter-rater first, and every
   disagreement enumerated. The calibration **exercise** has not run: no practitioner
   has labelled anything, so current weights still have not been compared with
   independently labelled real objects.
3. **Smallest slice** — Done: `@readme` recorded a public source and exact `YYYY-MM-DD`
   verification date for each encoded limit (2026-09-24). Done: `@scorer` defined the
   blinded calibration worksheet and its analysis (2026-09-24). Still open: two
   practitioners independently label a bounded 20–30 object sample without seeing tool
   scores, and the returned worksheets are analysed. That step needs humans and a real
   estate; nothing in the repository can substitute for it.
4. **Dependencies** — `@readme` owns limit documentation; domain rule owners confirm rule
   interpretation; `@scorer` owns calibration and any maths proposal; `@security`
   approves de-identification and retention. Sprint 5.2 supplies honest coverage.
5. **Validation** — Focused check: a documentation test fails when an encoded limit lacks
   a source/date; calibration records agreement and every disagreement (**mechanism met
   2026-09-24** — `tests/test_calibration.py` proves blinding removes every verdict
   field, sampling is deterministic and stratified, the agreement maths reproduces a
   published reference example, the degenerate cases return "undefined" rather than a
   flattering number, and every disagreement is enumerated rather than aggregated away;
   **no real labels recorded**). Release gate: limits are current and traceable
   (**met 2026-09-24**); any weight/threshold change has rationale, scorer sign-off,
   regression tests, and ruleset-version handling (**open** — the exercise has not run
   and no change is proposed). No change is required merely to increase agreement, and
   the analysis proposes none by construction.
6. **Risks and non-goals** — A small sample cannot establish universal validity and must
   not be tuned to improve one tenant. This sprint does not merge confidence into score,
   relabel `NOT_EVALUATED`, or alter blocking cap 39.
7. **Commit boundary** — Sourced limit records and their documentation gate are one
   boundary. Each accepted scoring change, ruleset increment, migration note, and
   regression test is a separate scorer-owned boundary.

### Sprint 5.4 — Prove Behavioural Data Agent Evaluation (proof first, 1–2 weeks)

1. **Outcome** — The project either demonstrates a read-only, reproducible route for
   executing a supplied synthetic corpus against a real agent, or records that the
   execution surface is unavailable, in which case **no `evaluation` evidence is
   produced at all** and the eight rules that read it stay `NOT_EVALUATED`: `AGT-006`,
   `AGT-007`, `AGT-008`, `AGT-009`, `AGT-010`, `AGT-011`, `AGT-012` and **`AGT-014`**
   ("Answer latency is acceptable and measured", which reads
   `evaluation.latency_p95_seconds`).

   **Written out in full on purpose — do not collapse this to a range.** The set is
   *not* contiguous: `AGT-013` sits between `AGT-012` and `AGT-014` and reads a declared
   use-case shape, not evaluation evidence. The notation `AGT-006…AGT-012` was wrong in
   two ways — it omitted `AGT-014` and it implied a range that does not exist — and range
   notation will silently re-acquire the same defect the next time the catalogue moves.

   **The distinction this sentence depends on.** The eight-rule answer is the
   **absent-`evaluation`-key** case, which is the one this sprint means: the execution
   surface was unavailable, so nothing was measured. It is **not** the empty-block case.
   Verified against the engine on a fixture complete in every other respect, varying only
   the evaluation surface:

   | Subject | Outcome |
   |---|---|
   | `evaluation` key **absent** | all eight `NOT_EVALUATED` |
   | `evaluation: {}` **present but empty** | `NOT_EVALUATED`: `AGT-007`, `AGT-008`, `AGT-009`, `AGT-014` — `FAILED`: `AGT-006`, `AGT-010`, `AGT-011`, `AGT-012` |

   That split is correct and must not be smoothed over: **a campaign that ran and
   recorded nothing is evidence of absence, not missing evidence.** An empty block is an
   assertion and four rules rightly fail on it. Only the absent key means *we could not
   look*. This is the same `FAILED`-versus-`NOT_EVALUATED` backbone the contract rests
   on, applied to Data Agent evidence.
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
   A versioned schedule contract now exists in `fabric/README.md` and `docs/INSTALL.md`;
   it defines cadence, `concurrency: 1` overlap prevention, identity requirement,
   schedule-run housekeeping, failure notification, and rerun procedure. The
   Bronze/Silver/Gold retention contract is documented as 90/180/730 days in
   `fabric_iq/lakehouse.py` and `docs/IDENTITY_AND_RETENTION.md`; durable run manifests
   and a tested, explicitly invoked pruning mechanism now exist, but no live deployment
   schedule invokes it. There is still no recorded unattended monthly cycle or proven
   scheduled run. Per the **Architecture Principle** above, the
   unattended run this sprint must prove is the Notebook executing inside Fabric against
   the `FabricIQReadiness` Lakehouse — a scheduled local CLI run, or a run writing to an
   external evidence folder, does not satisfy this sprint's outcome no matter how
   automated it is.
3. **Smallest slice** — The contract-definition slice is complete. The remaining
   smallest operational slice is for `@orchestrator` and `@lakehouse` to prove one
   unattended synthetic-safe run from that deployment-owned schedule contract before
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
   inputs demonstrably remain `NOT_EVALUATED`. **Open.** A provisional classification
   exists in [`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md), but it was obtained
   through a delegated over-privileged identity without prior scope approval and over two
   surfaces only, so it does not satisfy this criterion. Closing it requires the
   Sprint 5.1 re-run under an approved read-only service principal, with the identity
   that obtained each classification recorded alongside it.
2. All encoded product limits have a public source and exact verification date.
   **Met at this revision** for the fact itself: all eight rows in
   `docs/KNOWN_LIMITATIONS.md` §8 were individually re-verified 2026-09-24 against live
   Microsoft Learn / REST API reference pages (three source links were corrected in the
   same pass). This criterion does not require or imply the separate Sprint 5.3
   calibration sub-criterion (item 5 below covers score/threshold stability, not
   calibration); calibration is tracked under Sprint 5.3 and has not started.
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
9. Evidence-sink hygiene is executable, not manual: `python scripts/check_evidence_sinks.py`
   exits 0, asserting that every writer destination and documented output example
   resolves to a committed `.gitignore` rule, that no tracked file is shadowed by a broad
   ignore pattern, and that tracked content carries no tenant identifier, workspace or
   capacity GUID, UPN, or email outside synthetic placeholders. No CLI output flag steers
   a user toward a trackable location at its documented value. The check runs in CI as
   its own named step. **Met at this revision**, negative-tested; the destination and
   tracked-file counts are held in **Verified Repository Baseline**. It remains a
   heuristic that supplements, never replaces, the
   mandatory pre-push privacy audit.
10. Every documentation file that makes a privacy, identity, or retention claim — and
    every file a model reads as instruction, including a Skill — is claimed by exactly
    one agent, enforced by the explicit `REQUIRED_DOCS` map in
    `python scripts/check_agent_ownership.py`. **Met at this revision** (exit 0,
    negative-tested; the count is held in **Verified Repository Baseline**): adding or
    un-claiming such a file fails the build
    and names the required owner. The parser must be able to see the paths it is given;
    a dot-directory entry that matches nothing is a gate failing open, not a pass.
11. **No release-gate claim rests on an AI-facing file alone, and agent-facing
    instructions are never the sole source of operator guidance.** The tool is usable
    with no agent and no Skill present: the CLI output and human documentation stand on
    their own. Concretely — (a) every operational concept an operator needs to act on a
    verdict (reading order, the `NOT_EVALUATED` do-not-re-score rule, triage, and the
    non-obvious domain rules) exists in human documentation, not only in a Skill or
    agent file; (b) any AI-facing file that restates an engine constant is claimed in
    `REQUIRED_DOCS` and held to that constant by an executable drift check that matches
    the claim sentence, so a contradictory restatement cannot pass; (c) any guide path
    hardcoded by the CLI or the reports resolves to a file that exists and has an owner.
    **Met at this revision**, negative-tested: `tests/test_skill_drift.py` holds every
    value the Skill states to its engine constant, and `tests/test_standalone_guidance.py`
    holds the pointer, the owner, and the concepts — failing when the guide is deleted,
    stubbed, unclaimed, moved to a Skill, or stripped of a single concept, while a
    reasonable rewording still passes.

---

## Phase 6 — Consumption-Surface Readiness 🟥

**No Phase 6 release-gate criterion is met.** Every sprint below is **open** and none
may be marked closed. Since the phase was first recorded, three increments have landed —
the Sprint 6.1 availability record, the Scanner `endorsementDetails` carry, and the
endorsement rule family (`SEM-018`, `REP-011`) — and a non-normative `@scorer` design
note for Sprint 6.2 has been written. Those are progress inside an open sprint, not a
closed one. **Delivered work is named in each sprint's "Current evidence"; a criterion is
met only where the Release Gate says so, and today it says so nowhere.**

**Outcome.** A readiness verdict names the **consumption surface** it is about. An
organisation learns whether its estate is reachable by the Microsoft 365 surfaces that
are generally available today, by the in-Fabric agent surfaces, and by the preview
ontology workload — as distinct answers, not as one number.

**Concrete anchor.** The project is named `IsFabricReadyForIQ` and its 67 rules cover
tenant, workspace, semantic model, report and Data Agent objects. A documentation review
on 2026-09-24 (recorded below) found that the Microsoft 365 consumption surface — which
is **GA** — is assessed by nothing in the repository, while the Fabric IQ **ontology**
item, which is **preview**, is named in the product title and has zero rules. The
repository facts behind that statement were verified directly at that date:
`fabric_iq/models.py` declares exactly six `ObjectType` members and stops at
`DATA_AGENT`; the words `M365`, `Microsoft 365`, `Cowork` and `Copilot Chat` appear
nowhere in the repository except one unrelated `CHANGELOG.md` line; `python assess.py
--list-rules` at ruleset `2026.09.1` returned no endorsement rule and exactly one rule
mentioning geography, `TEN-006`. **Two of those facts have since changed** — see the
supersession note after the review — and the ontology and Microsoft 365 statements have
not.

**Falsifiable hypothesis.** The readiness properties that govern the GA Microsoft 365
path — two tenant settings, artifact endorsement and discoverability, and whether an
object's type is reachable at all — are either observable through the same read-only
surfaces this project already uses, or they are not, in which case the rules that depend
on them stay `NOT_EVALUATED` and the phase says so rather than inferring them.

**A second constraint the hypothesis did not anticipate.** Observability is necessary but
not sufficient. Type reachability is neither observable nor unobservable — it is
**documented**: a paginated report's unreachability by Cowork is a published product
behaviour, known without reading anything from the tenant. The blocker for that family is
therefore not collection but **vocabulary**: today's engine offers a rule exactly three
fates, and none of them states "in scope, known unreachable" without moving a score or a
coverage figure. That is recorded in Sprint 6.1 item 5 and item 7 below, and analysed in
the Sprint 6.2 design note.

**Cheap check.** Before any rule is written, `@collector` confirms whether the two
uncovered tenant settings and the item-level endorsement field are returned by an already
exercised read surface, and records the answer in
[`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md) with the identity that obtained it.
A setting that cannot be read is a documented blind spot, not a default-on assumption —
even though Microsoft documents one of the two as enabled by default. Encoding a vendor
default as an observed tenant value is exactly how a collection gap becomes a verdict.
**This check has run** (2026-09-25) and it returned the unwelcome answer for all three
gates; the endorsement half returned a usable field. Details in Sprint 6.1 item 3.

**Exit gate.** All five criteria in **Release Gate for Phase 6** are met; in particular,
no single headline verdict is presented as readiness for a consumption surface whose
reachability the run did not assess, and every ontology and Microsoft 365 rule without
confirmed evidence remains `NOT_EVALUATED` rather than passing or scoring zero.

### Documentation Review — 2026-09-24 — Fabric IQ Product-Fit Against Public Sources

**Not a sprint, and explicitly not a live-tenant observation.** It clears no Phase 5
gate, moves no Phase 5 criterion, and evidences no rule. It is recorded here on the same
terms as the **Exploratory Read** entry above: it produced durable knowledge that
constrains later design, and an unrecorded review is the kind of thing that gets
re-quoted later as something it was not.

1. **What happened** — A product-fit review compared this project's assessed scope with
   the documented Fabric IQ surface. Every fact below comes from a **public Microsoft
   Learn page read on 2026-09-24**. **None of it has been verified against a live
   tenant.** No API was called for readiness evidence, no tenant setting was observed, no
   object was assessed, and no fixture was produced. Product documentation states what a
   product is designed to do; it does not state what a given tenant is configured to do,
   and this project has never accepted the first as evidence of the second.
2. **The core finding — the GA/preview inversion** — *Microsoft IQ* is an umbrella of
   three layers: **Fabric IQ** (business entity and data context), **Work IQ** (Microsoft
   365 work context) and **Foundry IQ** (developer and agent grounding); Fabric IQ is a
   Fabric workload and the IQ workload is **preview**
   (`https://learn.microsoft.com/fabric/fundamentals/fabric-terminology#fabric-iq`,
   2026-09-24). Against that frame, the project's scope is inverted:
   - The **Fabric IQ plugin in Microsoft 365 Copilot Cowork is GA** and is **installed by
     default** in Cowork
     (`https://learn.microsoft.com/fabric/iq/connectors/cowork-overview`, 2026-09-24).
   - **Data answering from Power BI content in Microsoft 365 Copilot Chat is GA**
     (`https://learn.microsoft.com/fabric/iq/connectors/microsoft-365-copilot-overview`,
     2026-09-24).
   - The **ontology** item — the Fabric IQ semantic layer in OneLake carrying entity
     types, properties, relationships, constraints, data bindings to real OneLake data, a
     graph representation and a concept-level query surface — is **preview**
     (`https://learn.microsoft.com/fabric/iq/ontology/overview`, 2026-09-24).
   The GA surface is assessed by nothing; the preview artifact is in the product name.
   That ordering is the finding, and it is why Sprint 6.1 precedes Sprint 6.3.
3. **What the GA Microsoft 365 path actually depends on** — All from the two connector
   pages, read 2026-09-24:
   - **Three tenant settings gate the Copilot Chat path.** *Fabric data available in M365
     Copilot* lives in the **Microsoft 365 admin center** and is enabled by default.
     *Share Fabric data with your Microsoft 365 services* lives in the **Fabric admin
     portal** and controls whether Fabric proactively shares metadata; when it is off,
     Power BI content stops appearing in Copilot search and the item-attachment menu,
     though users can still paste links or name reports. *Data sent to Azure OpenAI can
     be processed outside your capacity's geographic region…* is required for tenants
     outside the United States and European Union. Of these three, **only the cross-geo
     setting has a rule** (`TEN-006`); the other two have none.
   - **Reachability is type-dependent.** Cowork grounds only on Power BI reports and the
     semantic models behind them. It does **not** ground on dashboards, paginated (RDL)
     reports, share links, a semantic model referenced directly by name, or other Fabric
     items — the page names **ontologies and data agents** among the excluded items.
     Copilot Chat likewise does not support paginated reports, dashboards, top-level apps
     or report **share links** (the resolved long-form URL is required), though a
     semantic model URL may be pasted.
   - **Discoverability is a ranking problem.** Cowork artifact discovery uses
     **endorsements, cross-item relationships and most-recently-used activity** as
     signals; it supports **Verified Answers** and schema selection, and reports in
     **workspace apps** are supported. The 65-rule catalogue contains **no endorsement
     rule**, so a property that decides whether the right report is found at all is
     currently unassessed.
   - **Answers carry no citation in Cowork.** Microsoft advises opening the source report
     to confirm a value before acting on it. Sensitivity labels propagate: the
     conversation takes the **most restrictive** label of any content used, and content
     Cowork subsequently creates — emails, meeting invites, files — **inherits** it.
   - **Copilot Chat prerequisites and security** — a **Microsoft 365 Copilot Premium**
     license for all users, plus Power BI permission and licensed access; **RLS and OLS**
     are both honoured.
4. **Three refinements this review made to its own starting statement** — recorded
   because a review that only confirms what it set out to confirm has not been run:
   - **DLP differs between the two GA surfaces.** The Copilot Chat page states DLP
     policies apply and can stop Copilot using Power BI content with a prohibited
     sensitivity label. The Cowork page states **DLP is not currently supported in
     Cowork**. Two GA surfaces, two different data-protection answers; any rule phrased
     as "M365 Copilot enforces DLP" would be wrong for one of them.
   - **The Copilot Chat exclusion of agents and ontologies is conditional, not
     absolute.** The page states Fabric data agents and ontologies "can't answer
     questions in Copilot Chat **without an explicitly published Microsoft 365 agent**".
     For **Cowork** the exclusion is unqualified. So the reachability statement must be
     made per surface: Cowork — not reachable; Copilot Chat — reachable only through an
     explicitly published Microsoft 365 agent.
   - **The ontology agent list has five entries, not four.** Alongside the **Fabric
     operations agent**, **Fabric data agent**, **Foundry IQ agent** and **Copilot Studio
     agent**, the page lists **custom agents using the ontology MCP server**
     (`https://learn.microsoft.com/fabric/iq/ontology/concepts-agent-integration`,
     2026-09-24). Separately, a Fabric data agent may use an **ontology as one of its
     data sources**, alongside a warehouse, lakehouse, Power BI semantic model, KQL
     database or mirrored database
     (`https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-copilot-studio-tool`,
     2026-09-24).
5. **The scoring-validity finding, which is the one that matters** — Cowork cannot reach
   data agents or ontologies at all. An organisation can therefore score **100/100 on all
   fifteen Data Agent rules and get nothing in Cowork**. The current headline verdict does
   not state *which consumption surface* it means, so four different reachability paths —
   Cowork, Copilot Chat, in-Fabric agents, and the ontology workload — are collapsed into
   one answer. This is the same category of error the **Non-Negotiable Contract** already
   forbids when it keeps eligibility, score and confidence separate and never lets one
   substitute for another. It is raised here as a `@scorer`-owned **design question**
   under Sprint 6.2, not as a defect to be patched quietly in a rule or a report.
6. **Repository gaps confirmed at this revision** — verified directly, not inferred:
   `ObjectType` has six members and **no `ONTOLOGY`**, and there are **zero ontology
   rules**; yet `fabric_iq/collectors/fabric_api.py` already enumerates the `Ontology`
   item type and already maps an `OntologyPreview/AgentsEnabled` tenant setting — the
   engine can **see** ontologies and never **judges** them. `M365`, `Microsoft 365`,
   `Cowork` and `Copilot Chat` occur nowhere in the repository outside one unrelated
   `CHANGELOG.md` line. Of the three gating settings only cross-geo is covered
   (`TEN-006`). There is no endorsement rule. All ten `REP-*` rules assess report
   **quality**; none assesses **reachability** by a consumption surface.
7. **Consequences carried forward** — Phase 5's sequence and blockers are unchanged.
   Nothing here evidences a field, so Sprint 5.1 is still the next actionable sprint and
   its prerequisite is still an authorised test tenant and an approved read-only service
   principal. Every fact above is a **documented product behaviour to be re-confirmed at
   implementation time**, with its verification date restated, exactly as
   `docs/KNOWN_LIMITATIONS.md` §8 requires of any encoded limit.

### Supersession Note — 2026-09-25 — What the 2026-09-24 Review Said That Is No Longer True

The review above is a **dated record** and is left as written; that is the point of
dating it. Two of its repository statements have since been overtaken, and one has been
sharpened. Nothing in this note closes a criterion.

- **"The 65-rule catalogue contains no endorsement rule" is no longer true.** `SEM-018`
  and `REP-011` shipped (`d208087`), both **MINOR**, fed by Scanner `endorsementDetails`
  which the collector now carries with absence treated as **unknown** rather than as
  "not endorsed" (`55bd8a7`). The catalogue is now **67 rules** at ruleset `2026.09.2`.
  The review's *reasoning* stands: discoverability was unassessed, and now one of its
  three signals is.
- **"Of the three gating settings only cross-geo is covered" is still true, and the
  reason is now worse than the review assumed.** The review treated coverage as a
  rule-authoring gap. The availability record (`d326e58`) shows it is a **collection**
  gap that rule authoring cannot close: see Sprint 6.1 item 3.
- **"All ten `REP-*` rules assess report quality; none assesses reachability" is still
  true** — there are now eleven `REP-*` rules and `REP-011` is also a quality rule. The
  count moved; the finding did not. Why no reachability rule exists is no longer merely
  "nobody wrote one": see item 5.

### Sprint 6.1 — Assess the GA Microsoft 365 Consumption Surface — 🟥 **OPEN**, partially started

**Status: open.** One of the three rule families has shipped, one is unevaluable at
source, and one is blocked on a decision that has not been made. The sprint closes when
all three have an honest disposition, and it has none yet.

| Rule family | Owner | State |
|---|---|---|
| Endorsement (`SEM-018`, `REP-011`, both MINOR) | `@semantic` | ✅ **Shipped** (`d208087`) |
| Tenant settings (the two uncovered M365 gates) | `@tenant` | 🟥 **Open — unevaluable at source.** Both gates are currently unreadable; a rule would be born `NOT_EVALUATED` |
| Type reachability (paginated reports, dashboards, agents, ontologies) | `@semantic` | 🟥 **Blocked on Sprint 6.2.** No rule outcome can express it today |

Ordered first on purpose, and the ordering is counter-intuitive. The artifact in the
product name — the ontology — is scheduled **last**, and the surface the product is not
named after is scheduled **first**. The reason is that Cowork and Copilot Chat are **GA
today** and completely unassessed, while the ontology workload is **preview** and will
keep changing shape under any rule written against it now. Assessing the stable,
shipping, unassessed surface before the moving, preview, named one is the cheaper and
more defensible order. It is also the smaller change: this sprint adds no object type.

1. **Outcome** — A run states whether the tenant's Microsoft 365 consumption path is
   open, and whether the estate is discoverable and reachable through it — or records
   explicitly that it could not tell.
2. **Current evidence** — **Open, with one family delivered.** What exists: the
   endorsement rules `SEM-018` and `REP-011` (`d208087`, both MINOR), the Scanner
   `endorsementDetails` carry that feeds them with absence treated as unknown
   (`55bd8a7`), and the availability record (`d326e58`). What does not exist: any rule
   over the two uncovered Microsoft 365 tenant gates — of the three documented gating
   settings only cross-geo is covered, by `TEN-006` — and **no rule flags an object whose
   type cannot be reached by either GA surface**, which item 5 explains is a vocabulary
   limit and not an oversight.
3. **Smallest slice** — ✅ **Delivered** (`d326e58`), and it returned the unwelcome
   answer. Not a rule: the first change was `@collector` establishing in
   [`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md) whether the gating settings and
   item-level endorsement are readable from surfaces this project already exercises. The
   record says **all three Microsoft 365 gates are currently unevaluable**:
   - *Share Fabric data with your Microsoft 365 services* (Fabric admin portal) —
     `permission-blocked`. No tenant-admin endpoint answered under the identity used, so
     this is a **scope** problem and is in principle recoverable by the Sprint 5.1
     authorised principal.
   - *Fabric data available in M365 Copilot* (Microsoft 365 admin center) — `absent`, and
     classified a **permanent blind spot**: it is administered in a different control
     plane, and **no widening of Fabric scope reaches it**. This one is not waiting on
     5.1 or on anything else in this repository. A rule over it is born `NOT_EVALUATED`
     and stays there.
   - The public reference does **not establish the `settingName`** for the Fabric-portal
     gate, so it is not even known whether that setting appears in the response at all.
     Guessing a key name and reporting `absent` when the guess misses would manufacture a
     blind spot; confirming the key is prerequisite work for `@collector`, not rule work.

   The consequence for sequencing: the **endorsement** half of this slice succeeded and
   its rules shipped; the **tenant-setting** half did not, so `@tenant`'s rules would
   today be three `NOT_EVALUATED` results. Writing them is defensible — a named blind spot
   beats a silent one — but it is a coverage cost with no score signal, and it must be
   taken deliberately rather than to make a sprint look finished.
4. **Dependencies** — `@collector` owns the availability record and any new read;
   `@tenant` owns tenant and workspace rules; `@semantic` owns report and semantic-model
   rules, including endorsement and reachability by type; `@readme` owns the Cowork and
   Copilot Chat product limits, which belong in `docs/KNOWN_LIMITATIONS.md` §8 style with
   a public source and an exact verification date — **this roadmap does not write them
   there and must not be cited as if it had**; `@security` reviews any new scope. Sprint
   5.1's identity prerequisite binds any live confirmation performed here.
5. **Validation** — Split by family, because the three families do not validate alike.
   - **Endorsement and tenant settings** (ordinary scored quality rules): focused check —
     synthetic present, absent, null, forbidden and malformed cases for each setting and
     for endorsement produce the expected evidence and rule outcome. Release gate: no
     Microsoft 365 rule passes on an unread setting, a documented vendor default is never
     substituted for an observed value, and every encoded Cowork or Copilot Chat limit
     carries a source and verification date.
   - **Type reachability**: ⚠️ **this criterion is not executable against today's engine,
     and the earlier version of this item was wrong to imply it was.** It previously read
     *"a fixture with a paginated report and a dashboard produces a reachability finding
     without altering either object's existing quality score"*. That is not a test anyone
     can write yet. `ScoringEngine.score_object` gives a rule outcome exactly three fates
     and there is no fourth:

     | Outcome | Score | Coverage | Finding emitted |
     |---|---|---|---|
     | `PASSED` / `FAILED` / `PARTIAL` | counts | counts | yes |
     | `NOT_EVALUATED` | no | **adds to `applicable_weight`, lowering coverage** | yes |
     | `NOT_APPLICABLE` | no | skipped before `applicable_weight` | yes |

     An honest `FAILED` on "unreachable by Cowork" enters the dimension mean and, at
     `MAJOR` or `BLOCKING`, applies a cap — a quality deduction, which item 6 forbids.
     `NOT_EVALUATED` is **not** the neutral escape hatch it looks like: it inflates
     `applicable_weight`, lowers coverage on every object the rule touches, and can push
     an object that was sitting just above the 50% publication floor into
     `NOT_EVALUATED` **status**. The score did not move and the verdict did — and it is
     also false, because a paginated report's unreachability is **documented, not
     unknown**. `NOT_APPLICABLE` is the only genuinely zero-impact outcome and it means
     *out of scope*; a paginated report is in scope and unreachable, so using it here
     would bend the engine's vocabulary to dodge a constraint this project refuses to
     dodge anywhere else.

     **The intent stands and is the reason the phase is worth doing:** reachability must
     not be a quality deduction. What was wrong was asserting it can be validated today.
     **What has to exist first** is a decision from Sprint 6.2 on where a reachability
     statement lives, and whatever engine or model change that decision implies. Only
     then does the criterion become writable, and its writable form is the stricter one
     the Sprint 6.2 design note proposes: a paginated report and a dashboard carry a
     reachability statement while `score`, `raw_score`, `status`, `eligible`,
     `confidence` and `coverage` stay **byte-identical** to the same fixture without the
     feature. Until 6.2 is decided, this family has **no focused check to run** — and
     that is the correct state to be in, not a gap to paper over.
6. **Risks and non-goals** — The Microsoft 365 admin center setting is **confirmed**
   unreadable from Fabric (item 3), so one of the three gates is permanently
   `NOT_EVALUATED`; that is an honest outcome and it is now a measured one rather than a
   risk. Cowork and Copilot Chat are moving GA surfaces and their limitation lists will
   change. This sprint does **not** assess Work IQ or Foundry IQ, does not evaluate
   Copilot answer quality, does not measure whether users find the right report, and does
   not license-check individual users.

   **The governing non-goal, restated as a constraint rather than a claim:**
   reachability must be a separate statement, never a quality deduction — an object is
   not worse-built because a consumption surface will not read its file type. **No
   mechanism in this repository can express that today** (see item 5). So this is a
   requirement on the Sprint 6.2 design, not a property this sprint may assert it
   upholds. The failure mode to guard against is a well-meaning reachability rule shipped
   as `NOT_EVALUATED` "for now": that quietly converts a documented product fact into a
   coverage loss, and coverage loss is this engine's word for *we could not see*, not for
   *we looked and the answer is no*.
7. **Commit boundary and the dependency between 6.1 and 6.2** — The availability record
   was a `@collector` boundary and landed first, alone (`d326e58`). The Scanner
   `endorsementDetails` carry (`55bd8a7`) and the endorsement rules (`d208087`) followed
   as separate boundaries with their own fixtures. Each remaining rule family is its own
   owner's boundary. The limitations documentation is a separate `@readme` boundary.

   **A correction to this item as first written.** It previously said the reachability
   rules *"may not be bundled with the Sprint 6.2 verdict change"*. **The dependency runs
   the other way.** The type-reachability family does not merely have to avoid 6.2 — it
   **depends on** 6.2, because until 6.2 decides where a reachability statement lives
   there is no outcome such a rule can honestly return (item 5). The two statements are
   not variants of the same caution: "must not be bundled" would permit shipping the
   rules first, which is precisely the mistake. Only that one family is blocked. The
   **tenant-setting** and **endorsement** families are ordinary scored quality rules
   about observable configuration and are unaffected by 6.2 — endorsement has already
   shipped ahead of it, which is the proof that the block is narrow.

### Sprint 6.2 — Separate Consumption Surfaces in the Verdict — 🟥 **OPEN**, design note written, decision not made

**A `@scorer`-owned design question, deliberately left undecided here.** This entry
states the problem and the constraint. It does not propose a shape, a field, a weight, a
new number, or a report layout, because pre-deciding the design in a planning document is
how a scoring change arrives without scorer review. The `docs/SCORING.md` note is
`@scorer`'s own analysis and is non-normative; this roadmap references it and neither
ratifies nor restates it.

**This sprint is now also a blocker, not only a successor.** Sprint 6.1's
type-reachability family cannot be written until this decision exists — see Sprint 6.1
item 5 and item 7. That inverts the dependency direction this roadmap originally
recorded between the two sprints.

1. **Outcome** — A reader can tell which consumption surface a verdict is about, and
   cannot mistake readiness for one surface as readiness for another.
2. **Current evidence** — **Open.** The engine produces one readiness verdict per run
   with no notion of a consumption surface. Because Cowork reaches neither data agents nor
   ontologies, an estate can score **100/100 across all fifteen Data Agent rules** and
   deliver nothing in Cowork; the verdict would not say so. Four reachability paths —
   Cowork, Copilot Chat, in-Fabric agents, the ontology workload — are currently collapsed
   into one answer. A `@scorer` design note now exists in `docs/SCORING.md` (§ *Design
   Note — Consumption-Surface Readiness (Sprint 6.2)*), **explicitly non-normative**. It
   is an input to the decision, not the decision.
3. **Smallest slice** — ✅ **Written, ❌ not ratified.** The slice was *"a design note
   reviewed alone"*: a `@scorer`-owned note in `docs/SCORING.md` stating the problem,
   enumerating candidate shapes with their failure modes, reviewed before any code moves.
   **The note is written; the decision is not made.** Those are different milestones and
   this roadmap will not merge them — a written note counts as the artifact, a ratified
   decision counts as the gate. Release-gate criterion 4 stays **open**.

   The note proposes a **per-surface reachability block orthogonal to the score**, and —
   to its credit — states its own strongest counter-argument: that `eligible` works
   precisely *because* it is load-bearing, while passive metadata nobody is forced to
   consult has no teeth. That tension is unresolved, it is `@scorer`'s to resolve, and
   **this roadmap does not resolve it, endorse a shape, or summarise the note as
   decided.** Read the note; do not read this bullet as a substitute for it. No engine,
   model or report change lands in the same increment as the note.
4. **Dependencies** — `@scorer` owns the shared data model, the maths and the decision;
   `@lakehouse` owns any downstream mart or report consequence and must not pre-empt it;
   `@preceptor` reviews whether the resulting output is defensible to an operator;
   `@readme` and `@remediation` follow the decision rather than anticipating it.

   **The relationship with Sprint 6.1 is bidirectional and must be read as two halves,
   not one ordering.** Sprint 6.1's **availability record** lands first — and has
   (`d326e58`) — so the verdict does not try to express inputs whose readability is
   unknown, and so a surface state derived from an unread setting is `not_evaluated`
   rather than a vendor default. But Sprint 6.1's **type-reachability rules** land
   *after* this decision, because they have no honest outcome until it is made. The
   endorsement and tenant-setting families sit on neither side of that and may proceed
   independently.
5. **Validation** — Focused check: a regression fixture in which an estate is strong on
   Data Agent rules and unreachable from Cowork must not produce an output a reader can
   read as "ready for Cowork". Release gate: whatever shape is chosen, eligibility, score
   and confidence remain three separate results; blocking cap 39, major cap 59 and the
   50% coverage floor keep their regression coverage; and an unassessed surface reports
   `NOT_EVALUATED` rather than contributing a flattering component.
6. **Risks and non-goals** — **The binding constraint: this must not become a single
   merged number.** Averaging per-surface readiness into one figure would recreate the
   exact defect it exists to fix, and adding a fourth headline result carries its own
   cost in comprehensibility — which is why the trade-off is `@scorer`'s to make and not
   this document's. Surface definitions will drift as Microsoft changes the products.
   Non-goals: this sprint invents no new severity, does not re-weight any existing rule,
   does not reinterpret `NOT_EVALUATED` as a low score, and does not hide an unassessed
   surface behind an assessed one.
7. **Commit boundary** — The design note is one boundary and is reviewed alone. Any
   accepted model or maths change is a separate `@scorer` boundary with a ruleset
   increment, migration handling and regression tests. Report and mart changes follow in
   a third, never in the same commit as the maths.

### Sprint 6.3 — Ontology as an Assessed Object Type (preview) — 🟥 **OPEN**, not started

Largest of the three, scheduled last, and the only one that adds an object type. It
assesses a **preview** workload, which changes what a rule is allowed to claim: a preview
surface that cannot be read must degrade to `NOT_EVALUATED`, and every encoded fact must
carry its source and exact verification date so a product change is detectable rather
than silently wrong.

1. **Outcome** — Ontologies are assessed as first-class objects, with readiness
   statements about their bindings, keys and relationships — or explicitly not assessed,
   with the reason recorded.
2. **Current evidence** — **Open.** `fabric_iq/models.py` declares six `ObjectType`
   members and has **no `ONTOLOGY`**; there are **zero ontology rules**. The asymmetry
   that makes this tractable: `fabric_iq/collectors/fabric_api.py` **already** enumerates
   the `Ontology` item type and **already** maps an `OntologyPreview/AgentsEnabled`
   tenant setting. The engine can see ontologies and never judges them, so the first
   increment extends judgement over evidence that collection already reaches, rather than
   opening a new read surface.
3. **Smallest slice** — Not the object type. The first change is a `@collector` record of
   what an ontology item actually returns beyond its name and type: whether entity-type
   keys, data bindings, time-series bindings and relationship bindings are exposed to a
   read-only caller at all. Documentation describes them
   (`https://learn.microsoft.com/fabric/iq/ontology/overview`, read 2026-09-24); nothing
   has confirmed they are **readable**. Only if that record shows readable fields does
   `@scorer` add the object type and a rule owner add the first rule. If it does not,
   the sprint's honest output is a limitation entry and no object type at all — an
   `ObjectType` with no readable evidence produces a scorecard-shaped hole, which is
   worse than no object type.
4. **Dependencies** — `@collector` owns the read record; `@scorer` owns the `ObjectType`
   addition and every downstream rollup consequence, since a new object type touches
   coverage, confidence and the marts; `@dataagent` owns the ontology-as-data-source
   relationship for Fabric data agents; `@lakehouse` owns mart and report impact;
   `@readme` owns dated sourcing of every preview fact; `@tester` owns fixtures. Sprints
   5.1 and 6.2 both precede this: the identity prerequisite governs any live read, and
   adding an object type before the verdict knows about consumption surfaces would bake
   the collapse this phase exists to undo.
5. **Validation** — Focused check: an ontology fixture with unbound time-series data,
   a missing multi-key entity-type key, and an unbound relationship type produces the
   expected findings, while an ontology with no readable binding metadata produces
   `NOT_EVALUATED` for every affected rule and **reduces object confidence** rather than
   scoring zero. Release gate: adding the object type moves no existing object's score;
   coverage, confidence and rollups account for the new type correctly; every encoded
   preview fact carries a public source and exact verification date; and the ruleset
   version increments with a migration note so trends do not silently join across it.
6. **Risks and non-goals** — **This is preview.** Generating an ontology from a semantic
   model leaves documented manual follow-up — bind time-series data, which is not created
   automatically; review entity-type keys and add missing ones, especially multi-key;
   bind relationship types to data; review the whole ontology for completeness
   (`https://learn.microsoft.com/fabric/iq/ontology/concepts-generate`, read 2026-09-24).
   Those are the natural rule candidates and they are also the most likely to change
   before GA. A preview API may not exist, may be gated, or may change shape between
   runs. Non-goals: this sprint does not author ontologies, does not generate or repair
   bindings, does not evaluate ontology answer quality, does not assess Foundry IQ or
   Work IQ, and does not let a preview object type contribute to a readiness score on
   evidence it could not read.
7. **Commit boundary** — The read record is one `@collector` boundary and comes first.
   The `ObjectType` addition with its rollup, coverage and mart consequences is a single
   `@scorer`-led boundary — a new object type is never split across commits, because a
   half-registered type is invisible to exactly the checks that would catch it. Each rule
   family and its fixtures follow separately. Dated preview sourcing is a `@readme`
   boundary.

### Sprint 6.4 — Grounding Sources as Assessed Subjects (`Lakehouse`, `KQLDatabase`) — 🟥 **OPEN**, blocked on Sprint 5.1, adds no Phase 6 release criterion

**Why this sprint exists.** `@dataagent`'s 2026-09-25 triage of the scope ledger answered
Q1 and Q2 and routed **Q6** here: *which sprint owns the source-as-subject object type and
its collection prerequisite.* Ledger rows 10 (`Lakehouse`) and 11 (`KQLDatabase`) are
**open** — in scope as subjects, unassessable today — and they named Sprint 5.1 as a
prerequisite and Sprint 6.3 as a pattern while **no sprint owned them**. `@dataagent`
refused to invent a sprint number, calling it *"the scheduling equivalent of a reasonless
exclusion"*, which is correct and is why the decision is recorded here. **The decision: give
them a home, blocked, rather than record them as an unowned gap.** An open row whose closing
path is fully described but belongs to nobody decays into the same silence the ledger was
built to end; a numbered sprint that cannot start until a named proof lands does not. The
document already uses that shape twice — 7.4 is numbered and blocked on 5.1, 7.5 on a
ratified 6.2 — so this is the existing convention, not a new one. **The scope basis is
`@dataagent`'s and is not re-litigated here**: *the assessed subject is the artefact the
source binding names, and it is a subject where a readiness fact lives on that artefact and
cannot be observed from the agent.* This sprint schedules that ruling; it does not review it.

**Why Phase 6 and not Phase 5 or 7.** The work is an object-type addition on the Sprint 6.3
pattern — the pattern the rows themselves name — and 6.3 is where object-type additions
live. It is not Phase 5 work: Phase 5 closes evidence, and 5.1 already owns the collection
half (below). It is not Phase 7 work: Phase 7 counts subjects and adds no object type, by a
property it must keep.

1. **Outcome** — A lakehouse and a KQL database that a Fabric data agent grounds on carry
   readiness statements of their own — table and column metadata, naming, descriptions,
   whatever the read record shows is legible — instead of being judged only through the
   agent's declaration about them. `AGT-001` and `AGT-005` judge the agent's *declaration*
   (supported type, reachability, routing text authored on the agent); nothing today reads
   the artefact the generated SQL is actually written against.
2. **Current evidence** — **Open, and blocked at the collection layer.** Ledger rows 10 and
   11 record the ruling and the obstacle in one sentence: *"In scope as a subject,
   unassessable today: Sprint 5.1 first (no exercised endpoint returns that metadata)."*
   `fabric_iq/models.py` has no `LAKEHOUSE` and no `KQL_DATABASE` member; there are zero
   rules. Unlike 6.3's ontology case, the asymmetry that makes a sprint tractable is
   **absent**: the collector enumerates both item keys, but enumeration gives a name and a
   type, not the table and column metadata the readiness fact lives in. **No exercised
   endpoint has been shown to return it.** That is an unverified API surface, and this
   roadmap does not plan a capability on one.
3. **Smallest slice** — **Not the object type, and not in this sprint.** The first slice
   belongs to Sprint 5.1 and is a scope extension of it, not new work here: add
   *lakehouse and KQL-database table/column metadata for a read-only caller* to 5.1's
   target surface list, so its API reality record answers whether the metadata is readable
   at all, under which identity and scope, and at what grain. 5.1 is already the sprint that
   establishes what endpoints return, and rows 10 and 11 already name it. **Only if that
   record shows readable fields** does `@scorer` add the object types and a rule owner write
   the first rule. If it does not, this sprint's honest output is a dated limitation entry,
   an updated ledger reason, and **no object type at all** — an `ObjectType` with no readable
   evidence produces a scorecard-shaped hole, which is worse than no object type. That is
   6.3's rule applied unchanged.
4. **Dependencies** — **Hard prerequisite: Sprint 5.1**, which carries an unchanged external
   blocker (an authorised test tenant and an approved read-only service principal). Nothing
   in this sprint may proceed by assuming a field. `@collector` owns the read record and the
   5.1 scope extension; `@scorer` owns the `ObjectType` additions and every rollup, coverage
   and confidence consequence; `@dataagent` owns the scope ruling already given and the
   agent-to-source relationship; `@lakehouse` owns mart and report impact; `@tester` owns
   fixtures; `@readme` owns the ledger rows, which move from **open** to **assessed** or to a
   dated exclusion only when this sprint resolves — and never before.
5. **Validation** — Focused check: a fixture whose lakehouse exposes no readable table
   metadata produces `NOT_EVALUATED` for every affected rule and **reduces object
   confidence**, rather than scoring zero; a fixture with readable metadata produces the
   expected findings. **Sprint exit gate:** either (a) both object types exist, every
   existing object's score is byte-identical to the same fixture before the addition,
   coverage/confidence/rollups account for the new types, the ruleset version increments
   with a migration note, and ledger rows 10 and 11 read **assessed** with rule IDs; or
   (b) the read record shows the metadata is unreadable, a dated limitation entry says so,
   and rows 10 and 11 carry that as their recorded reason. **(b) closes this sprint as
   legitimately as (a).** A sprint that can only close by shipping is a sprint that will
   ship on unverified evidence.
6. **Risks and non-goals** — **This sprint adds no Phase 6 release-gate criterion, and
   Phase 6 may close with it open.** Phase 6's gate is about consumption surfaces and the
   ontology type; silently adding a sixth criterion would move that phase's closure
   condition, which is not this change's business — the ledger rows, not the phase gate,
   are what keep this visible, and that is what the ledger is for. The substantive risk is
   subject inflation: every grounding source is a potential object type, and the test above
   is the only thing stopping the catalogue from growing to the shape of the Scanner
   response. A source earns a subject only where a readiness fact lives on it and is
   invisible from the agent. Non-goals: no eventhouse subject (ledger row 12 excludes it as
   the wrong grain, `@dataagent`, review by 2026-12-24); no warehouse or SQL-endpoint
   subject (row 9's derived-surface basis is unchanged); no data-quality assessment of the
   tables themselves; no claim that these rules would evaluate answer quality, which is L5
   and stays `NOT_EVALUATED` until Sprint 5.4.
7. **Commit boundary** — The 5.1 scope extension rides in `@collector`'s 5.1 work and is
   not a commit here. The read record is one `@collector` boundary and comes first. The
   `ObjectType` additions with their rollup, coverage and mart consequences are a single
   `@scorer`-led boundary — both types together or neither, for the reason 6.3 states: a
   half-registered type is invisible to exactly the checks that would catch it. The ledger
   row updates are a `@readme` boundary and land last, because a row may not claim
   **assessed** before the rules exist.

## Release Gate for Phase 6

The phase closes only when all of the following are executable or evidenced. **All five
are open.** One rule family (endorsement: `SEM-018`, `REP-011`) and two supporting
records have landed inside Sprint 6.1, and the Sprint 6.2 design note has been written —
**none of that meets a criterion below.** **Sprint 6.4 adds no criterion here**: it was
opened on 2026-09-25 to give scope-ledger rows 10 and 11 an owner, it is blocked on
Sprint 5.1, and this phase may close with it open. The count below stays **five**
deliberately; if a reader ever needs a sixth, that is a `@scorer` decision and a separate
change.

1. Every consumption surface the tool names in a verdict has at least one assessed
   input, and every surface it does **not** assess is stated as unassessed rather than
   omitted. **Open.**
2. The two currently uncovered Microsoft 365 gating settings each map to a confirmed
   field or to an explicit unavailable classification recorded with the identity that
   obtained it, and a documented vendor default is never stored as an observed tenant
   value. **Open.** The classifications now exist (`permission-blocked` and a permanent
   `absent`, `d326e58`), but the criterion also requires the mapping to be expressed in
   the run — no rule consumes either gate yet, and the Fabric-portal `settingName` is not
   established, so it is not known whether that setting appears in the response at all.
3. Type reachability is reported separately from object quality: a paginated report or a
   dashboard is flagged as unreachable by a GA surface **with every quality figure on its
   scorecard unchanged** — `score`, `raw_score`, `status`, `eligible`, `confidence` and
   `coverage` identical to the same fixture without the feature. **Open, and blocked —
   not merely unstarted.**

   **This criterion is not satisfiable by the current engine, and the version of it
   first recorded here was wrong to imply otherwise.** `ScoringEngine.score_object`
   offers a rule outcome three fates and no fourth: `PASSED`/`FAILED`/`PARTIAL` move the
   score; `NOT_EVALUATED` leaves the score alone but raises `applicable_weight` and so
   lowers coverage estate-wide, which can push a marginal object through the 50%
   publication floor into `NOT_EVALUATED` **status** — a changed verdict, and a falsehood
   besides, since a paginated report's unreachability is documented rather than unknown;
   `NOT_APPLICABLE` is the only zero-impact outcome and means *out of scope*, which an
   in-scope unreachable object is not.

   **The criterion is retained deliberately.** Its intent — reachability is a statement,
   not a deduction — is what makes the phase worth doing, so it is not deleted or
   weakened. **What must exist first** is a ratified Sprint 6.2 decision and whatever
   engine or model change it implies. Until then this criterion has no executable form,
   and anyone proposing to satisfy it with a `NOT_EVALUATED` reachability rule is
   proposing to trade a documented fact for a coverage loss. It cannot be met by Sprint
   6.1 alone.
4. The per-surface verdict decision is made by `@scorer`, recorded in `docs/SCORING.md`,
   and does not merge surfaces into a single number; eligibility, score and confidence
   remain three separate results throughout. **Open.** A design note exists in
   `docs/SCORING.md` and is **explicitly non-normative**; this criterion requires a
   **decision**, and writing down the candidate shapes is not making one. Do not credit
   this criterion on the strength of the note.
5. Ontology rules, if any exist, degrade to `NOT_EVALUATED` without readable evidence,
   carry a public source and exact verification date for every preview fact, and their
   introduction increments the ruleset version with a migration note. **Open.**

---

## Phase 7 — Scope-Drift Detection 🟡

**Two of five sprints are delivered and one release criterion of seven is met.** Sprints
7.1 (the ledger) and 7.2 (the offline reconciliation gate) landed on 2026-09-25;
criterion 2 is met and the other six are open. Sprints 7.3–7.5 have not started. The
phase still adds **no rule, no object type and no scoring change** — that property is
deliberate and survives delivery, so nothing below may be cited as coverage. What is now
true that was not: an omission in the one declared source is a signed, dated, checked
decision rather than a silence. What is still true: the phase detects shape the
repository already names, and nothing else.

**Outcome.** The repository notices when Fabric grows something the rule catalogue does
not assess, and says so out loud, instead of staying silently green.

**Three kinds of decay, and the one nothing watches.**

| Decay | Example | Watched today by |
|---|---|---|
| A product fact changes | A documented limit moves | `docs/KNOWN_LIMITATIONS.md` §8 — a public source and an exact verification date per fact, all eight rows re-verified 2026-09-24 |
| An API surface changes | An endpoint gains or loses a field | [`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md) — and only as far as one tenant, one identity, one day reaches |
| **The product's shape changes** | A new item type, a new consumption surface, a new agent kind | **Partly, since 2026-09-25.** [`SCOPE_LEDGER.md`](SCOPE_LEDGER.md) records a disposition for every element of `WORKSPACE_ITEM_KEYS` and `scripts/check_scope_ledger.py` enforces it offline — for that **one** declared source only. Tenant settings, object types, consumption surfaces and agent kinds are still watched by nothing, and no verdict states scope (7.5) |

The third is the dangerous one, and it is dangerous in a way the first two are not. A
stale limit produces a wrong answer, which is embarrassing and findable. A shape change
produces *no* wrong answer: every fact in the catalogue stays true, all 67 rules keep
evaluating exactly what they were written to evaluate, and the thing they evaluate
quietly stops being the whole subject. **A catalogue can be 100% accurate and 100%
irrelevant**, and until 2026-09-25 nothing in this repository could tell those two states
apart for any source at all. It can now tell them apart for one.

**Concrete anchor — it already happened twice, and a human found it both times.** The
2026-09-24 product-fit review recorded in Phase 6 found that the **GA** Microsoft 365
consumption surface (the Cowork plugin, Copilot Chat data answering) was assessed by
nothing, and that the **preview** ontology item — the artifact this product is named
after — had zero rules while `fabric_iq/collectors/fabric_api.py` **already** enumerated
`Ontology` in `WORKSPACE_ITEM_KEYS` and **already** mapped an
`OntologyPreview/AgentsEnabled` tenant setting in `TENANT_SETTING_MAP`. The engine could
see ontologies and never judged them. At that moment the test suite was green, the
documentation gate was green, the ownership gate was green and the evidence-sink gate was
green. **It took a user asking "how does this fit with Cowork?" to surface a blind spot
on generally available functionality.** Phase 7 exists because that question was the only
detector in the system, and a question is not a gate.

**Falsifiable hypothesis, and its result.** The part of Fabric's shape that the
repository *already names in its own code* can be reconciled against the rule catalogue
**entirely offline** — no tenant, no network, no service principal — and every element
that is enumerated but unassessed can be listed exactly. The hypothesis is falsified if
that list turns out to be long and dominated by elements nobody would ever assess, in
which case the reconciliation is noise and the phase's real work is the disposition
record, not the check. **Result (2026-09-25): not falsified, and the noise half was
wrong in an instructive direction.** The offline reconciliation is real — `check_scope_ledger.py`
runs with no tenant and no network. Of the ten unassessed elements, triage sorted four to
`open` and five to dated exclusions with one still untriaged; the list was not dominated
by never-assess items, because **two of the three this roadmap named as obviously
never-assess were wrong**. See the cheap check below.

**Cheap check, and it already half-falsifies the hypothesis.** Reading the constants
takes minutes and can be done before any ledger or gate exists. `WORKSPACE_ITEM_KEYS`
carries **13** item containers; exactly **three** (`reports`, `datasets`, `DataAgent`)
reach an assessed `ObjectType`; **ten** are enumerated and judged by nothing — `Ontology`
among them, but so are `Notebook`, `Lakehouse` and `SQLAnalyticsEndpoint`, which nobody
has claimed should carry readiness rules. `fabric_iq/models.py` declares **six**
`ObjectType` members while the **Verified Repository Baseline** records rules against
**five**: `CAPACITY` is declared and carries none. So a naive reconciliation fires eleven
times on day one, of which perhaps two are real. **That settles the sprint order**: the
baseline record comes first and the check second, because a check shipped against an
empty baseline is a check that is red on arrival, and a check that is red on arrival is
muted within a month.

**What the triage found, and why the guess above is left standing.** The sentence
"`Notebook`, `Lakehouse` and `SQLAnalyticsEndpoint`, which nobody has claimed should
carry readiness rules" was a planner's guess, and on 2026-09-25 `@dataagent`'s triage
overturned two thirds of it. `Notebook` and `SQLAnalyticsEndpoint` were excluded with
reasons (rows 8 and 9). **`Lakehouse` was not**: it is now ledger row 10, **open** and
in scope as a subject, alongside `KQLDatabase` (row 11), on the test that *the assessed
subject is the artefact the source binding names, and it is a subject where a readiness
fact lives on that artefact and cannot be observed from the agent*. A documented data
agent grounds on a lakehouse, and the table and column metadata the generated SQL is
written against is a fact about the lakehouse that no rule reads. The guess is left in
place rather than rewritten because it is the evidence for the sprint order above: the
"perhaps two are real" estimate was the reason to write the ledger before the check, and
**the estimate was low**. A planner who had shipped the check first would have been
arguing about `Lakehouse` while the build was red.

**Where drift strikes.** Using the layer model that frames this project's coverage — L0
physical, L1 structural, L2 lexical, L3 semantic, L4 ontological, L5 behavioural, L6
consumption — this phase watches the **boundaries** of L0, L4 and L6: a new item type is
a new L0 subject, the ontology item is the L4 subject with zero rules, and a new
consumption surface is an L6 reader nobody assessed. It watches none of L1–L3, because
those are properties of objects already in scope and the catalogue already judges them,
and it cannot watch L5, whose quality question is `NOT_EVALUATED` by design until Sprint
5.4's proof exists. The model earns its place here for one reason only: it shows that a
catalogue can be complete at L1–L3 and still be answering about the wrong set of objects.

**The trap, named before the work starts.** A detector nobody can act on is decoration.
This is the same failure the Skill's drift gate had before Sprint 5.0.1, and exactly the
failure `@scorer` designed the ruleset fingerprint around: *a guard that fires on typo
fixes teaches contributors to regenerate it reflexively, and a guard people regenerate
without reading is decoration*. If this detector fires on every Fabric release note, or
on every commit that touches a collector, it will be muted within a month and the
repository will be worse off than before — because a muted gate produces the appearance
of coverage. Three design constraints keep the ratio honest, and all three are release
criteria below, not aspirations: **fire on transitions only** (a new untriaged element or
an expired disposition, never on steady state); **no bulk re-dating command**, so clearing
a fire costs one deliberate per-row edit with a reason; and a **noise budget** — a fire
cleared without a recorded decision is counted as a gate failure, not as a pass.

**Exit gate.** All seven criteria in **Release Gate for Phase 7** are met; in particular,
no element of a declared shape source is untriaged, every deliberate exclusion carries a
reason, an owning agent and a review-by date, and no scope statement moves a score, a
coverage figure or a confidence figure — nor is any of it mapped to `NOT_EVALUATED`,
which reports missing evidence and never an absent rule. **Criterion 2 is met at this
revision; the other six are open.**

### Sprint 7.1 — Record What We Deliberately Do Not Assess (the scope ledger) — 🟡 **DELIVERED 2026-09-25** (`662c50b`), sprint stays **OPEN**

1. **Outcome** — One record states, for every element of Fabric's shape the repository
   already names, exactly one disposition: **assessed** (with rule IDs), **deliberately
   excluded** (with a reason, an owning agent and a review-by date), **open** (with the
   sprint that would close it), or **untriaged** — the state that must be empty. The
   scope of a verdict becomes something an owner signed, rather than a by-product of
   which collector happened to be written first.
2. **Current evidence** — **Delivered, and open.** [`SCOPE_LEDGER.md`](SCOPE_LEDGER.md)
   exists, is owned by `@readme`, is the eighth `REQUIRED_DOCS` entry, and disposes all
   **13** elements of `WORKSPACE_ITEM_KEYS`: **3 assessed** (`reports`, `datasets`,
   `DataAgent`), **4 open** (`dashboards`, `Ontology`, `Lakehouse`, `KQLDatabase`),
   **5 deliberately excluded** with a reason, an owning agent and a review-by date
   (`dataflows`, `datamarts`, `Notebook`, `SQLAnalyticsEndpoint`, `Eventhouse`), and
   **1 untriaged** (`GraphModel`). **The sprint stays open on that single row**, which is
   exactly what release criterion 1 describes closing, and it is held on a *collection*
   question, not a rule question: Q3 to `@collector` — whether the Scanner key
   `GraphModel` denotes the Fabric graph item. `@dataagent` ruled Q1 and Q2 and
   deliberately declined to apply a ruling to a name whose referent is unverified, which
   is the discipline row 9's own `SQLAnalyticsEndpoint` correction records. Signing a
   disposition for a name you cannot resolve is the reasonless exclusion this sprint was
   written to prevent, arriving by the back door.
   **What this replaced:** before 2026-09-25 nothing of the kind existed, and the finding
   was the asymmetry itself — 13 item containers enumerated against 3 assessed; 6 settings
   in `TENANT_SETTING_MAP`; 6 `ObjectType` members against 5 with rules — **none of it
   recorded anywhere as a decision**, so the repository's scope read identically whether
   an omission was considered and rejected or never noticed. That is precisely why the
   ontology gap survived: the evidence of it sat in a constant the collector maintains by
   hand. Two of the three asymmetries are still in that state; only the first is now
   signed.
3. **Smallest slice** — Not the gate, and not all sources. Hand-write the ledger once for
   **one** source, `WORKSPACE_ITEM_KEYS`, thirteen rows. This is the cheapest possible
   test of whether a disposition can be written at all: if `@tenant`, `@semantic` and
   `@dataagent` cannot say in one sentence each why `Notebook` is excluded and `Ontology`
   is not, then automating the comparison would only make an unanswerable question fail
   the build faster.
4. **Dependencies** — An owner decision comes first: the ledger asserts a
   **collection-capability claim** and is therefore a `REQUIRED_DOCS` document, so
   whichever agent owns it must be added to the map in `scripts/check_agent_ownership.py`
   **in the same change**. `@readme` is the proposed owner (it already owns release-claim
   accuracy and the dated-sourcing discipline of §8), with `@collector` supplying the
   item-type rows and `@tenant`/`@semantic`/`@dataagent` supplying dispositions for their
   object types; `@tester` owns the entry check. The required-document count moves 7 → 8
   in that commit and nowhere earlier. **No dependency on Sprint 5.1 or 6.2**: reading
   this repository's own constants needs neither a tenant nor a verdict-shape decision.
5. **Validation** — Focused check: every element of the declared source resolves to
   exactly one disposition; a row marked excluded carries a reason, an owning agent and a
   review-by date, and a row carrying none fails review. Release gate: no element is
   untriaged and no exclusion is undated. **Note what this does not close** — a ledger is
   the baseline a detector needs, not a detector. Closing 7.1 closes nothing in 7.2.
6. **Risks and non-goals** — The real risk is that the ledger becomes somewhere to park
   inconvenient truth: an exclusion reading "out of scope" with no reason is *worse* than
   silence, because it looks decided. The reason field, the named owner and 7.3's review
   obligation are the mitigation, and a reviewer should treat a reasonless exclusion as a
   finding. Non-goals: no rule, no object type, no scoring change, no claim that an
   excluded item type is unimportant, and no attempt to enumerate item types the
   repository has never heard of — that is 7.3 and 7.4.
7. **Commit boundary** — The ledger, its `REQUIRED_DOCS` entry and its ownership test are
   one commit. A required document that is unclaimed for even one commit is the
   gate-failing-open case Sprint 5.0.1 found. No rule module and no test of the engine is
   touched.

### Sprint 7.2 — Make the Ledger Executable (offline reconciliation) — ✅ **DELIVERED 2026-09-25** (`e185aab` / `f3162ca` / `fa561a3`)

1. **Outcome** — A check fails the build when a shape element appears in code with no
   disposition, or when a disposition's review date has expired, and is silent otherwise.
2. **Current evidence** — **Delivered.** `scripts/check_scope_ledger.py` exists, imports
   `WORKSPACE_ITEM_KEYS` rather than re-typing it, and asserts five facts (listed in
   **Per-Change Quality Gate**). It runs offline in CI as its own named step on all four
   legs, is listed in the per-change gate, and `tests/test_scope_ledger_gate.py`
   negative-tests all three required directions plus a vanished declaring module. It is
   the one Phase 7 release criterion that is met (criterion 2), on the ground that the
   check is **executable and unskippable**; how much shape it *reaches* is criterion 1's
   and 7.3/7.4's business and is not credited here. The precedent this was built on —
   `scripts/check_agent_ownership.py` and `scripts/check_evidence_sinks.py`, both
   `@tester`-owned, each enumerating from code against an explicit map — also carried the
   warning that was heeded: Sprint 5.0.1 found the ownership parser could not begin a path
   with a dot, so the gate reported clean over a file it had never read.
3. **Smallest slice** — One source (`WORKSPACE_ITEM_KEYS`), one failure mode (an element
   with no disposition), exit 1 naming the element and the agent who must triage it.
   Expiry checking is the second slice, not the first. **Import the constant; never
   re-type the list** — a gate holding its own copy of the thing it guards drifts from it,
   and the drift is invisible in exactly the direction that matters.
4. **Dependencies** — `@tester` owns the script and its tests and adds the module
   ownership claim (modules move 27 → 28 in that commit); `@orchestrator` is involved only
   if the check joins the documented per-change gate list, which it should. Sprint 7.1 is
   a hard prerequisite. Independent of 5.1 and 6.2.
5. **Validation** — Focused check: **three** negative tests, because two of them are the
   ones that matter. (a) Plant a new key in the enumerated source → exit 1 naming it.
   (b) Back-date a disposition past its review date → exit 1. (c) Remove a declared source
   entirely → exit 1, because a source that disappears must not read as "nothing to
   check". Release gate: the check runs in CI as its own named step, is listed in the
   per-change gate, and each negative test is recorded as having been run and observed to
   fail. A gate that cannot fail is not a gate.
6. **Risks and non-goals** — The reflexive-regeneration trap is the design risk and is
   handled by omission: **there is deliberately no bulk `--update` or `--accept-all`
   flag.** The cost is manual work on every fire, and that cost is the point. The check
   must also **never read the network**: a CI gate that fetches a vendor page is
   non-deterministic, breaks the standard-library-only contract, and fails in the place
   people trust most. Non-goal: detecting anything the repository does not already name.
7. **Commit boundary** — Script, tests, module-ownership claim and gate-list entry in one
   commit. No engine, model or rule file is touched.

### Sprint 7.3 — Schedule the Attention Code Cannot Pay — 🟥 **OPEN**, not started, **unblocked and next in Phase 7**

1. **Outcome** — The classes of shape that exist only as prose — consumption surfaces,
   agent kinds, GA/preview status, item types announced but not yet enumerated here —
   carry a dated review obligation, so that the **absence of a review** becomes a build
   failure even though the product change itself is invisible to any check.
2. **Current evidence** — **Open.** This is the sprint that covers the miss the other
   sprints structurally cannot, and the asymmetry must be stated plainly because it
   decides how much the automated half is worth: **of the two 2026-09-24 findings, an
   offline reconciliation would have caught the ontology one and would *not* have caught
   Cowork.** `Ontology` sat in a constant the repository maintains, so the gap was
   visible in the code's own vocabulary. The Microsoft 365 consumption surface appeared in
   no constant, no endpoint and no item key — at that date the words `M365`,
   `Microsoft 365`, `Cowork` and `Copilot Chat` appeared nowhere in the repository except
   one unrelated `CHANGELOG.md` line. **No amount of self-reconciliation finds a thing the
   repository has never mentioned.** The mechanism that would have caught it is a
   calendar, and the precedent for it already works: `docs/KNOWN_LIMITATIONS.md` §8, a
   public source and an exact verification date per fact.
3. **Smallest slice** — One class, three rows: the Microsoft 365 surfaces (Cowork and
   Copilot Chat), the in-Fabric agent surfaces, and the preview Fabric IQ workload — each
   with a public source, a checked date and a review-by date. 7.2's expiry check covers
   them with no new mechanism, which is why this sprint follows that one. **Cadence
   proposal: 90 days**, and the reasoning is a noise argument, not a preference. Three to
   five reviewable classes on a quarterly cycle fire a handful of times a year, each fire
   costing one human one reading pass; a monthly cadence quadruples the fires without
   quadrupling the product's rate of shape change, and an annual one leaves a blind spot
   that outlives most planning horizons. If a review repeatedly finds nothing, lengthen
   the cadence and record why — do not delete the row.
4. **Dependencies** — `@readme` owns the dated sourcing, being already accountable for the
   §8 discipline; `@roadmap-planner` converts any finding into a sprint; `@tester`'s 7.2
   expiry check supplies the mechanism — **and that mechanism now exists** (delivered
   2026-09-25), so this sprint's stated prerequisite is met and it is the **next
   actionable Phase 7 sprint**. No tenant, no 5.1, no 6.2. Being unblocked is not the
   same as being started: nothing below has been done.
5. **Validation** — Focused check: a row whose review-by date has passed fails the 7.2
   check naming the row and its owner; the same row re-dated with a source and a date
   passes. Release gate: **a review that found nothing is itself evidence and must be
   written down** with its date and the sources consulted — otherwise the next reviewer
   cannot distinguish a checked surface from an unchecked one, which is the exact
   confusion this phase exists to remove. **Open.**
6. **Risks and non-goals** — This is a calendar, not a detector. It fails silently when a
   human reads carelessly, and that failure cannot be negative-tested. Its honest claim is
   narrow: it guarantees that somebody looked on a stated date, never that they saw.
   Non-goals: no automated release-note ingestion, no network call in a gate, and no
   treatment of a vendor documentation page as an observation of a tenant — the roadmap
   already forbids that conversion and this sprint does not create an exception to it.
7. **Commit boundary** — The review-obligation rows and their sourcing are a `@readme`
   documentation boundary. No mechanism change belongs here; if the expiry check needs
   work, that work is 7.2's.

### Sprint 7.4 — Notice an Item Type the Tenant Has and the Collector Does Not — 🟥 **OPEN**, blocked on Sprint 5.1

1. **Outcome** — A real estate carrying an item container this collector does not
   recognise produces a recorded, visible statement instead of a silent drop.
2. **Current evidence** — **Open and blocked.** The normaliser iterates
   `WORKSPACE_ITEM_KEYS`; a container outside that tuple contributes to no count and is
   reported by nothing, so a genuinely new Fabric item type sitting in a scanned workspace
   is invisible to the run and to the operator alike. Whether unrecognised containers
   actually appear, and under what key spelling, is **unknown**: the Scanner was not
   exercised at all by the 2026-09-24 exploratory read.
3. **Smallest slice** — `@collector` records in [`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md)
   whether a Scanner workspace payload carries containers outside the known tuple, and
   records **key names only** — never contents, because an unknown container's contents
   are un-triaged tenant evidence of unknown sensitivity. A counting mechanism follows
   only if unrecognised keys are actually observed.
4. **Dependencies** — Inherits Sprint 5.1 **in full**: an authorised tenant, a read-only
   service principal whose scopes and evidence expiry `@security` approves beforehand, and
   the expiry set at authorisation rather than afterwards. `@collector` owns the record.
   This sprint may not be simulated from fixtures and called done — a synthetic payload
   with an invented key proves the code path, not the product.
5. **Validation** — Focused check: a fixture workspace carrying an unknown container
   yields a scope statement while `score`, `raw_score`, `status`, `eligible`, `confidence`
   and `coverage` stay identical to the same fixture without it. Release gate: the live
   record exists under the approved identity, or the criterion stays open. The code-path
   criterion and the observation criterion are **two criteria on purpose**; a fixture
   proof closes the first and never the second.
6. **Risks and non-goals** — An unknown key may be a preview flighting artefact, a
   per-SKU difference, or a spelling variant of a type already known. Classifying it as a
   new item type would **manufacture** drift, which is the mirror image of missing it:
   record the key, do not interpret it. Non-goals: no rule, no object type, no score
   effect, and no logging of container contents at any verbosity.
7. **Commit boundary** — The collector's availability record is one boundary and comes
   first; any counting mechanism and its fixtures follow separately. No live payload or
   identifier is committed.

### Sprint 7.5 — Say It in the Verdict — 🟥 **OPEN**, blocked on a ratified Sprint 6.2 decision

1. **Outcome** — An operator reading a verdict can see the **assessment's own scope**:
   which artifact types were assessed, which were present and not assessed, and which were
   deliberately excluded — as a statement, never as a score.
2. **Current evidence** — **Open, blocked, and last on purpose.** A verdict today is
   silent about its own scope, so an estate full of unassessed item types reads exactly
   like an estate the catalogue fully covers. This project's discipline is that missing
   evidence is `NOT_EVALUATED` and never a pass; the analogue at catalogue level is that
   an unassessed artifact type must be **visibly absent**, not silently absent.
3. **Smallest slice** — Not code. `@scorer` records the requirement and its constraint
   against the Sprint 6.2 decision: a scope statement is a property of the **run**, not an
   outcome of a **rule**, and it must leave `score`, `raw_score`, `status`, `eligible`,
   `confidence` and `coverage` identical — the same zero-impact constraint as Phase 6
   criterion 3. The options, with their costs, stated here and **not decided**:
   - **(a) Gate script only** (`scripts/`, CI). Cheapest; no engine change; no interaction
     with 6.2; catches staleness at commit time, which is when the catalogue actually goes
     stale. Cost: **invisible to the operator** — it protects the repository and not the
     reader.
   - **(b) Run output only** (console, structured output, Gold mart). Reaches the reader.
     Cost: model and reporting changes owned by `@scorer` and `@lakehouse`, a mart column,
     and it lands squarely in the verdict shape that Sprint 6.2 owns and has not decided.
     It also arrives late: a catalogue goes stale in git months before anyone runs.
   - **(c) Both, with the gate as the source of truth.** The pattern already proven by the
     Skill drift check — one constant, an executable check holding every restatement to
     it. Cost: two surfaces and one consistency test to keep them from contradicting.
   **Recommended sequencing, which is a recommendation and not a decision:** take (a)
   inside 7.2, hold (b) until 6.2 is ratified, and adopt (c) only after the ledger has
   survived one full review cycle without being muted. The reason for the hold is
   structural — a scope statement in a verdict *is* a verdict-shape change, and Phase 6
   already forbids making one before 6.2 decides.
4. **Dependencies** — `@scorer` owns the verdict shape and where this requirement lands;
   `@lakehouse` owns mart and report impact; `@preceptor` should rule on whether an
   unstated scope is a review dimension. Hard prerequisite: a **ratified** Sprint 6.2
   decision. **Nothing in this sprint may pre-empt, anticipate or modify that decision**,
   and the non-normative note in `docs/SCORING.md` is not released by anything written
   here.
5. **Validation** — Focused check: a fixture containing an unassessed present type
   produces a scope statement while every quality figure on every scorecard is byte-identical
   to the same fixture without the feature. Release gate: the statement appears in console
   output, structured output and the mart; it is never counted in coverage and never
   mapped to a rule outcome.
6. **Risks and non-goals** — The strongest risk is vocabulary collapse in two directions:
   a reader who sees "not assessed" and reads "failed", and an implementer who reaches for
   `NOT_EVALUATED` because it is the nearest existing fate. It is neither. `NOT_EVALUATED`
   says a rule's evidence was missing; `NOT_APPLICABLE` says an object was out of scope; a
   scope statement says **no rule was ever written for this kind of thing**. Non-goals: no
   new rule outcome, no cap, no coverage effect, no per-surface merge.
7. **Commit boundary** — After 6.2 only, as a single `@scorer`-led boundary covering
   model, engine, reporting and marts together — the same rule 6.3 applies to an object
   type, and for the same reason: a half-registered concept is invisible to exactly the
   checks that would catch it.

### What This Phase Cannot Detect

Stated here rather than discovered later, because a detector that is vague about its
reach invites the assumption that silence means currency.

- **A change Microsoft has not documented**, or has not shipped into a surface this
  project reads. Nothing in 7.1–7.5 has any purchase on it.
- **A change whose significance is a judgement call.** A capability added *inside* an
  existing item type moves no item key, no setting name and no object type. Copilot
  gaining a new answer path over an existing semantic model is invisible to every sprint
  here — the shape is unchanged and only the meaning moved.
- **A change in a control plane this project cannot reach.** The *Fabric data available in
  M365 Copilot* gate is already classified a permanent blind spot administered elsewhere;
  drift inside it is equally permanent.
- **Its own blind spot.** A new source of shape added to the code without being registered
  with the ledger is undetected by construction. 7.2's third negative test narrows this
  and does not close it.
- **Whether an assessed thing is assessed *well*.** This phase counts subjects, never
  quality. L5 behavioural quality remains `NOT_EVALUATED` by design until Sprint 5.4
  produces a real execution proof, and no scope statement may be read as a quality claim.

**It narrows the hole; it does not close it.** Silence from this detector means one thing
only: nothing changed in the places we already know how to look, and nobody's review came
due. It does not mean Fabric stood still.

## Release Gate for Phase 7

The phase closes only when all of the following are executable or evidenced. **Criterion 2
is met at this revision (Sprint 7.2); the other six are open.**

1. Every element in every declared shape source carries exactly one disposition, and the
   untriaged set is empty. **Open** — and it is now open on **one row and one question**,
   not on a backlog. Twelve of the thirteen elements of `WORKSPACE_ITEM_KEYS` are
   disposed; row 13 (`GraphModel`) is untriaged, held on **Q3 to `@collector`** —
   whether that Scanner key denotes the Fabric graph item. It is **not** waiting on a
   `@dataagent` answer: Q1 and Q2 were ruled on 2026-09-25, and `@dataagent` declined to
   apply the ruling to a name whose referent is unverified, which is the same discipline
   the ledger's own `SQLAnalyticsEndpoint` correction records. The criterion's other half
   is untouched by that answer: **only one shape source is declared**, so "every declared
   shape source" is today a statement about `WORKSPACE_ITEM_KEYS` alone, and closing row
   13 would satisfy the untriaged half while leaving the reach half to 7.3/7.4.
2. The reconciliation check runs offline in CI as its own named step, appears in the
   per-change quality gate, and is negative-tested three ways — a new untriaged element, an
   expired disposition, and a declared source that has vanished. **Met (2026-09-25,
   Sprint 7.2).** `scripts/check_scope_ledger.py` runs as the CI step *Check the scope
   ledger disposes every element in code* on all four legs, is listed in **Per-Change
   Quality Gate** above, and `tests/test_scope_ledger_gate.py` negative-tests all three
   directions (`test_a_new_key_with_no_row_fails_and_is_named`,
   `test_a_back_dated_review_fails_and_is_named`, and
   `test_a_missing_constant_fails_rather_than_reporting_clean` with
   `test_a_declaration_pointing_at_a_module_that_is_gone_fails`). This criterion is about
   the check being *executable and unskippable*; it says nothing about how much shape the
   check reaches, which is criterion 1's and 7.3/7.4's business.
3. Every deliberate exclusion carries a reason, an owning agent and a review-by date. No
   exclusion is permanent by construction, and an undated one fails the check rather than
   being grandfathered. **Open.**
4. **Historical replay.** Against a fixture of the repository's shape sources as they
   stood before 2026-09-24, the check fires on the `Ontology` asymmetry — and the same test
   records that it does **not** fire on the Microsoft 365 surface, naming 7.3's review
   obligation as the only mechanism that covers that class. A detector claiming both
   misses would be lying about its own reach, and the test exists to stop that claim being
   made later. **Open.**
5. **Noise budget honoured.** Over one full review cycle, every fire traces one-to-one to
   a recorded triage decision or a completed review. A fire cleared by re-dating without a
   recorded decision counts as a gate failure, not a pass. If the check fires on changes
   unrelated to product shape, the check is wrong and is fixed or withdrawn — contributors
   are not asked to absorb it. **Open.**
6. No scope statement moves `score`, `raw_score`, `status`, `eligible`, `confidence` or
   `coverage`, and none is mapped to `NOT_EVALUATED`, `NOT_APPLICABLE` or any other rule
   outcome. **Open.**
7. No part of the detector reads the network, requires a tenant, or depends on a
   non-standard-library package. The live half (7.4) is a **separate** criterion and stays
   open until an approved read-only identity produces its record; the offline half may not
   be credited for it. **Open.**

Closing the phase also requires publishing **What This Phase Cannot Detect** where
operators read it — `@readme`, in `docs/KNOWN_LIMITATIONS.md` — because a detector shipped
without its limits is precisely the decoration this phase exists to avoid.

## Sequencing and Release Policy

`5.0 evidence-sink hygiene ✅ → 5.0.1 standalone operability ✅ → (2026-09-24 exploratory
read — knowledge only, clears no gate) → 5.1 API proof (next, open)
→ 5.2 evidence reconciliation → 5.3 facts/calibration → 5.4 agent proof
→ 5.5 operational re-measurement`

`(2026-09-24 documentation review — knowledge only, clears no gate) → 6.1 availability
record ✅ + endorsement family ✅ → 6.2 per-surface verdict **decision** (note written,
undecided) → 6.1 type-reachability family (blocked until 6.2 decides) → 6.3 ontology
object type (preview) → 6.4 grounding sources as subjects (blocked on 5.1)`

`(2026-09-24 product-fit review — a human found both gaps and the repository found
neither) → 7.1 scope ledger ✅ (open on one untriaged row) → 7.2 offline reconciliation
gate ✅ → 7.3 dated review
obligation → 7.4 tenant-observed unknown item types (blocked on 5.1) → 7.5 scope
statement in the verdict (blocked on a ratified 6.2)`

The 6.1 tenant-setting family is unsequenced against 6.2: it is blocked on collection,
not on the verdict shape, and may land whenever its inputs become readable — or be
written deliberately as a named blind spot.

- Sprint 5.0 is closed. It gated the live-tenant sprints: no proof run against a real
  tenant starts before every writer default and documented output path is confirmed
  ignored, and that condition is now asserted by `scripts/check_evidence_sinks.py` on
  every change rather than by a one-off review.
- Sprint 5.0.1 is closed. It is assurance over 5.0's surfaces, not a capability
  increment, and it does not displace 5.1 or shorten its work. It carries no external
  blocker, which is precisely why it could be done while 5.1 waits.
- Sprint 5.1 is therefore the next actionable sprint, and it is **open**. Its only
  blocker is external: an authorised test tenant and read-only service principal. Until
  that exists, 5.1 cannot be started and no later sprint may substitute for it by
  assuming a field. The 2026-09-24 exploratory read does **not** advance it: an
  observation made under a delegated over-privileged identity, with scope and retention
  review after the fact, is knowledge to re-test, not a gate that ran.
- Sprint 5.3 limit verification did not wait for 5.2: it closed 2026-09-24
  (`docs/KNOWN_LIMITATIONS.md` §8), independent of 5.1/5.2 status, exactly as this
  sequencing policy allows. Scoring calibration, the sprint's other half, still waits
  for honest coverage.
- Sprint 5.4 implementation is conditional on its API proof; a failed proof produces an
  explicit limitation, not a substitute design.
- Sprint 5.5's schedule-contract definition has landed early, but its proof run and
  release gate wait for the preceding evidence and scoring gates.
- Ruleset-incompatible runs are not plotted as improvement/regression. They require a
  new baseline or an explicit migration approved by `@scorer`.
- **Phase 6 does not jump the queue.** Phase 5's external blockers are unchanged by it:
  5.1 still needs an authorised test tenant and an approved read-only service principal,
  5.4 still needs its API proof, and 5.5 still depends on both. A documentation review
  changes none of that, because reading a product page is not observing a tenant.
- Like Sprint 5.0.1, **some Phase 6 work carries no external blocker** — fixtures, the
  `@scorer` design note and dated limitation sourcing are all repository work — so it
  could proceed while 5.1 waits. That is a scheduling convenience and nothing more: **it
  does not substitute for 5.1 and closes no Phase 5 criterion.** Any Phase 6 slice that
  needs a live confirmation inherits Sprint 5.1's identity prerequisite in full and waits
  behind it. **This bullet previously said "most Phase 6 work" and generalised "rule
  authoring" as unblocked; that was too broad.** Of the three Sprint 6.1 rule families,
  one shipped, one is blocked on collection (and one of its gates permanently so), and
  one is blocked on an internal design decision. Repository work being *possible* is not
  the same as a rule being *writable*.
- Within Phase 6 the order is deliberate and counter-intuitive: the **GA** Microsoft 365
  surface (6.1) precedes the **preview** ontology workload (6.3), even though the
  preview artifact is the one in the product name. Assess the shipping surface that
  nothing currently covers before the moving surface that will change shape under any
  rule written against it today.
- Sprint 6.3 must not start before 6.2 has a recorded decision. Adding an object type
  while the verdict still collapses every consumption surface into one number would bake
  in the defect Phase 6 exists to remove. **A written design note is not a recorded
  decision**; the note in `docs/SCORING.md` is non-normative and does not release this
  constraint.
- **Sprint 6.1 does not cleanly precede 6.2.** The roadmap originally sequenced 6.1
  wholly before 6.2 and, in 6.1 item 7, forbade bundling the reachability rules with the
  6.2 change — which reads as "6.1 first, carefully". That is backwards for one of the
  three families. 6.1's availability record precedes 6.2; 6.1's **type-reachability
  rules depend on 6.2** and cannot be written before it, because no rule outcome in
  today's engine states "in scope, known unreachable" without moving a score or a
  coverage figure. The endorsement family proved the split is real by shipping ahead of
  6.2 without touching it.
- **Sprint 6.4 is new (2026-09-25) and changes no blocker.** It exists to give
  scope-ledger rows 10 (`Lakehouse`) and 11 (`KQLDatabase`) an owner after `@dataagent`
  ruled them in scope as subjects and correctly declined to invent a sprint number for
  them. It is **blocked on Sprint 5.1** in full — its readiness fact lives in table and
  column metadata that **no exercised endpoint has been shown to return**, so its first
  slice is a question added to 5.1's target surface list, not work of its own. It adds
  no Phase 6 release criterion and Phase 6 may close with it open. **Opening a sprint is
  not progress on it**, and numbering it must not be read as evidence that the metadata
  exists.
- **Phase 7 does not jump the queue either, and changes no blocker.** Sprint 5.1 still
  needs an authorised test tenant and an approved read-only service principal, 5.4 still
  needs its API proof, 5.5 still depends on both, and the Sprint 6.2 decision is still
  unratified — nothing in Phase 7 decides it, and 6.1's type-reachability family still
  waits behind it. Sprints 7.1–7.3 carry **no external blocker** because they read this
  repository's own constants and its own review dates, which is the same scheduling
  convenience Sprint 5.0.1 had and carries the same warning: **it closes no Phase 5 or
  Phase 6 criterion.** 7.4 inherits 5.1's identity prerequisite in full and 7.5 waits for
  a ratified 6.2. **Sprints 7.1 and 7.2 have now landed (2026-09-25) and the prediction
  held**: they closed no Phase 5 and no Phase 6 criterion, and every external blocker
  above is exactly where it was before them.
- Within Phase 7 the order is forced by the noise argument, not by preference: the
  **ledger precedes the check**. A reconciliation shipped against an empty baseline fires
  on eleven of the thirteen enumerated item containers on its first run, of which about
  two are genuine gaps, and a gate that is red on arrival teaches contributors to clear it
  without reading. 7.3 follows 7.2 because the expiry mechanism it needs is built there.
  **The order was right and the estimate was low.** Triage produced four `open` rows and
  one still untriaged, not two genuine gaps: `Lakehouse` and `KQLDatabase` — both named
  above as items nobody would assess — turned out to be in scope and now need Sprint 6.4.
  A check shipped first would have made that argument with the build red.
- **Why this was chosen ahead of the ontology layer, and what deferring it costs.**
  Sprint 6.3 is the ontological layer — entity types, bindings, relationships — and it is
  the layer this product is named after. Phase 7 was scheduled first for two reasons:
  it is **unblocked**, needing no tenant, no principal and no undecided verdict shape; and
  it protects every later phase, 6.3 included, from going quietly out of scope. The cost is
  real and is not cancelled by either reason. Deferring 6.3 means the named artifact keeps
  **zero rules** for at least another cycle; an organisation that has generated an ontology
  from a semantic model gets no readiness statement about the manual follow-up Microsoft
  documents — time-series bindings, multi-key entity-type keys, relationship bindings; and
  the project's name keeps promising more than its catalogue delivers, a gap one outside
  question already exposed once. Two things make the trade defensible without making it
  free: the ontology workload is **preview** and will change shape under any rule written
  against it today, so deferral also avoids re-writing; and Phase 7 converts the omission
  from a silent one into a recorded, dated, reviewable one — the difference between a gap
  and a blind spot. **No part of Phase 7 assesses a single ontology, and none of it may be
  cited as progress on 6.3.**

## Risks Across the Phase

| Risk | Mitigation / release consequence |
|------|----------------------------------|
| Metadata is absent, preview-only, or SKU-specific | Prove first; classify honestly; keep affected rules `NOT_EVALUATED`; do not close the relevant gate. |
| One-tenant observations are over-generalised | Record tenant/SKU bounds and require target-environment validation before a complete-assessment claim. |
| More fields increase apparent score | Review confidence and outcomes separately; collection changes do not justify threshold changes. |
| Calibration sample contains customer data | De-identify, retain outside git, and obtain Security approval before use. |
| Scheduler cannot be represented portably | Document the environment-owned deployment step and validate it live; do not claim repository-provisioned scheduling. |
| Ruleset changes break trend comparability | Start a new baseline or use an explicit compatible migration; never silently join versions. |
| A fact is known but the engine has no outcome that can state it | Do not force it into `NOT_EVALUATED` — that reports *we could not see* for something we did see. Block the rule, record the blocker, and fix the vocabulary first. This is the Sprint 6.1 type-reachability case. |
| Documentation drifts from implementation | Run the documentation gate before and after each increment; bounded claims block release when evidence is missing. |
| Documentation, help text, or a flag default creates privacy exposure without any change to collection code | The 2026-09-23 audit exposed evidence through a documented example path, not through a collector. Treat docs, CLI help, and output defaults as part of the privacy surface: `scripts/check_evidence_sinks.py` asserts on every change that every writer and output flag is ignored at any supplied value, that no example steers output to a trackable location, and that tracked content holds no real identifier — including on documentation-only changes. |
| Unowned documentation carries unaccountable privacy claims | Closed by Sprint 5.0. `scripts/check_agent_ownership.py` now audits `fabric_iq/` modules **and** an explicit `REQUIRED_DOCS` set, so `docs/IDENTITY_AND_RETENTION.md` (@readme), `docs/INSTALL.md` and `fabric/README.md` (@orchestrator), and `docs/SELF_ASSESSMENT.md` (@preceptor) each have exactly one owner, and an unowned required document fails the build. Any new document asserting a privacy, identity, or retention claim must be added to that map in the same change; the set is explicit precisely so that coverage cannot lapse silently. |
| Data already pushed cannot be un-ignored | Hardened ignore rules protect the future only. The 2026-09-23 exposure was resolved by the user deleting and recreating the public repository: the orphaned commit returns 404 and the republished history is 21 commits with 0 occurrences. Any *future* pushed identifier again requires an authorised human decision — record it as open rather than describing the repository as clean. |
| Local evidence outlives the run that produced it | Resolved for the known case on 2026-09-24: `artifacts/checkpoint.json` from the 2026-09-21 live run, five live run outputs carrying real UPNs, three reports rendering real workspace names, and two duplicate run triplets were **destroyed**; `artifacts/` in the checkout now holds synthetic output only, and the evidence still needed lives outside the repository and outside any synced folder with an expiry of 2026-10-08. The standing rule that prevents a recurrence: **a proof run receives its expiry at authorisation, not afterwards** — an expiry decided later is a decision nobody is scheduled to make. Closed. |
| Two read surfaces enumerate different objects, and neither says so | Observed on 2026-09-24: the OneLake listing and the catalog search returned **disjoint** workspace sets, 0% overlap on GUID and on case-folded display name. A single-surface collector would have reported a complete-looking tenant while omitting everything the other surface saw. Mitigation is a Sprint 5.2 design constraint: union surfaces on the GUID, record which surface saw each object, and give a single-surface object reduced coverage rather than unqualified presence. Never let enumeration breadth be inferred from one endpoint answering `200`. |
| An inventory is keyed on a field that looks like an identifier and is not | On one surface `id` is a display-name string and the GUID is carried separately. Keying a normalizer on `id` by convention would key on a mutable name and break cross-surface joins **without raising**. Key on the GUID; assert the key shape in the normalizer so a wrong key fails loudly. |
| An exploratory read gets re-quoted later as gate evidence | The 2026-09-24 read was authorised, useful, and **not** a Sprint 5.1 proof: scopes and retention were reviewed afterwards and the identity was delegated and over-privileged. The mitigation is placement and labelling — the finding is recorded as an exploratory read, the matrix carries the caveat at its head, criterion 1 stays open, and the sprint states what still blocks it. A finding may be kept without the gate it failed to satisfy being quietly credited. |
| Operator knowledge lives only in an AI-facing file, so the tool stops working without an agent | Release-gate criterion 11. Human documentation is the source and the Skill is the pointer, never the reverse: `docs/INTERPRETING_RESULTS.md` carries the reading order, the `NOT_EVALUATED` rule and the triage table, the reports print a `HOW TO READ THIS` block, and both are owned in `REQUIRED_DOCS`. A capability that only works when a model is in the room is not a capability this tool ships. |
| A hand-written AI-facing file contradicts the engine it describes | `docs/RULES.md` is generated and checked; a Skill is not. `tests/test_skill_drift.py` holds every stated value to the imported constant and matches on the claim sentence over every occurrence, so a stale or contradictory number fails the build instead of being quoted to a model as authoritative. Any new AI-facing file restating a constant must arrive with its drift assertion. |
| A gate fails open rather than failing loudly | Sprint 5.0.1 found the ownership claim parser could not begin a path with a dot, so a `.github/...` entry matched nothing and the check reported clean while covering it. Negative-testing a gate must include *what it cannot see*, not only what it rejects: every new gate needs a test that proves it detects the absence it exists to detect. |
| One verdict answers for several consumption surfaces that reach different objects | Recorded 2026-09-24: Cowork reaches neither data agents nor ontologies, so an estate can score 100/100 on all fifteen Data Agent rules and deliver nothing in Cowork. A single headline verdict that does not name its surface is four answers collapsed into one — the same defect the contract already forbids when it keeps eligibility, score and confidence separate. Sprint 6.2 is the `@scorer`-owned decision; the binding constraint is that the fix must **not** be a merged per-surface number. |
| A documented product default is stored as an observed tenant value | *Fabric data available in M365 Copilot* is documented as enabled by default, and it lives in the Microsoft 365 admin center, not the Fabric admin portal. Assuming the default because the setting is hard to read would convert a collection gap into a verdict. An unread setting is `NOT_EVALUATED`; a vendor default is never evidence about a tenant. |
| A rule is written against a preview surface as though it were stable | The Fabric IQ workload and the ontology item are preview at 2026-09-24. Sprint 6.3 schedules the read-confirmation before the object type, requires `NOT_EVALUATED` without readable evidence, and requires a public source with an exact verification date on every encoded preview fact so a product change is detectable rather than silently wrong. |
| Product documentation is mistaken for tenant observation | The 2026-09-24 product-fit review read public Microsoft Learn pages and called no API for readiness evidence. Documentation states what a product is designed to do, never what a tenant is configured to do. The review is recorded as a documentation review, clears no Phase 5 gate, and every fact it carries is marked for re-confirmation at implementation time. |
| The catalogue stays 100% accurate and stops describing the product | Phase 7. Every encoded fact can remain true while the subject moves: on 2026-09-24 an unassessed **GA** consumption surface and an unassessed **preview** item the collector already enumerated were both found by a user's question, with the full test suite and all four gates green. A rule count is never evidence of relevance. Record what is deliberately not assessed, date every exclusion, and fail the build when an element is untriaged or a review comes due. |
| A drift gate fires so often that contributors mute it | The failure `@scorer`'s ruleset fingerprint was designed around: a guard that fires on typo fixes teaches reflexive regeneration, and a guard people regenerate without reading is decoration. Phase 7's detector fires only on transitions — an untriaged element or an expired disposition — never on steady state; it ships **no** bulk re-dating command, so every fire costs a deliberate per-row edit; and its noise budget is a release criterion, where a fire cleared without a recorded decision counts as a gate failure. If it fires on changes unrelated to product shape, the check is fixed or withdrawn rather than tolerated. |
| A detector is trusted for reach it does not have | Phase 7 sees only shape the repository already names, plus the staleness of human attention. It cannot see an undocumented change, a capability added inside an existing item type, or a control plane it cannot reach — and an offline reconciliation would have caught the ontology gap while missing Cowork entirely. Publish the limits alongside the detector, and read its silence as "nothing moved where we know how to look", never as "nothing moved". |

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
- Shipping operator guidance that exists only in a Skill or an agent-facing file, or
  restating an engine constant in an AI-facing file without an executable drift check.
- Rewriting pushed git history, or disposing of locally retained tenant evidence,
  without an explicit authorised human decision.
- Crediting a release gate to a run that did not meet its stated preconditions —
  including any read taken under an over-privileged or delegated identity, or before
  `@security` approved its scopes, retention and expiry.
- Assessing **Work IQ** or **Foundry IQ**. This project assesses the Fabric estate and
  the surfaces that consume it; the other two Microsoft IQ layers are named here only to
  place Fabric IQ correctly, never as scope.
- Stating readiness for a consumption surface the run did not assess, or letting one
  surface's result stand in for another's.
- Treating a documented product default, a Microsoft Learn statement, or any other
  vendor documentation as an observation of a tenant's configuration.
- Fetching vendor release notes, or making any network call, from inside a repository
  gate. A check that depends on a remote page is non-deterministic and unrunnable
  offline, and this project's gates are neither.
- Treating an unassessed artifact type as a failure, a low score, or a coverage loss; or
  reading a recorded exclusion as a statement that the excluded thing does not matter.
- Claiming that a scope-drift check detects Fabric product change in general. It detects
  shape the repository already names, and reviews that have come due.

## Per-Change Quality Gate

```powershell
python assess.py --list-rules
python scripts/build_rules_doc.py --check
python scripts/check_agent_ownership.py
python scripts/check_evidence_sinks.py
python scripts/check_scope_ledger.py
python -m unittest tests.test_docs
python -m unittest tests.test_evidence_sinks
python -m unittest tests.test_skill_drift
python -m unittest tests.test_standalone_guidance
python -m unittest tests.test_self_assessment
python -m unittest discover -s tests -t .
```

In addition, verify internal links and compare documented rule/test counts with command
output.

`check_agent_ownership.py` covers both `fabric_iq/` modules and the `REQUIRED_DOCS`
documentation and Skill set; `check_evidence_sinks.py` covers writer destinations,
tracked-file shadowing, and tracked identifiers; `check_scope_ledger.py` covers scope
drift **for the sources it declares and for nothing else** — today that is the single
constant `WORKSPACE_ITEM_KEYS` (13 keys), and `TENANT_SETTING_MAP`, `ObjectType`,
consumption surfaces and agent kinds are deliberately **not** watched by it (Sprints
7.3/7.4). Read "every declared source constant" as "the one that is declared", never as
"everything". Within that scope it asserts five facts: the ledger table parsed and the
number of rows parsed equals the number the document states; every declared source still
imports to a non-empty sequence; every element of every declared source carries exactly
one disposition in `docs/SCOPE_LEDGER.md`; no row disposes an element the code no longer
names; and every `deliberately excluded` row carries a review-by date that has not passed
— an undated exclusion fails too, because one that never comes back is permanent by
neglect rather than by decision. It never reads the network and has no bulk `--update`
flag by design — the manual cost on every fire is the point. One consequence a
contributor should know before reading a red build as a flake: the **five** current
exclusions (ledger rows 6, 7, 8, 9 and 12) are each dated `2026-12-24`, and the
comparison is `review_by < as_of`, so this check **passes on 2026-12-24 and fails on
2026-12-25 with nobody having changed a line** — all five at once, named individually.
Verified by running `audit()` at both dates: 0 expiries as of 2026-12-24, 5 as of
2026-12-25. Clearing it costs a deliberate per-row edit with a recorded decision, and
the rows are not all one agent's to clear: rows 6–9 (`dataflows`, `datamarts`,
`Notebook`, `SQLAnalyticsEndpoint`) are owed by **`@readme`**, row 12 (`Eventhouse`) by
**`@dataagent`**, and the check names the owner in each message. That is the review
obligation working. It runs in CI as its own named step,
*Check the scope ledger disposes every element in code*, with exactly the command above;
`tests.test_skill_drift` covers the
values the Skill restates; `tests.test_standalone_guidance` covers the property that the
tool works with no Skill present. All exit non-zero and name the offending path,
address, owner, stated value, or unhomed concept. None may be skipped on a
documentation-only change — the 2026-09-23 exposure arrived through a documented
example, not through code, and an AI-facing file is a documentation-only change that a
model will act on.

Any change that adds or moves an output path — a writer, a CLI output flag, or a
documented example command — must also register that path with
`scripts/check_evidence_sinks.py` so the destination is asserted rather than assumed. The
underlying manual probes remain useful when diagnosing a failure of that check:

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
`@security` classifies it. These checks and scans are heuristics — they supplement the
mandatory pre-push privacy audit and never replace it.

A live-tenant or schedule claim requires external evidence and cannot be closed by unit
tests alone. Before any push, run the mandatory privacy/provenance audit; this roadmap
update itself is not a request to commit or push.
