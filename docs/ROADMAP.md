# Roadmap — IsFabricReadyForIQ

Owner: **@roadmap-planner**. This document is authoritative for scope and release gates.

Last evidence review: **2026-09-24** against ruleset `2026.09.1`.

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
| Scoring and backlog | Explainable scorecards, CSV/JSON backlog, owner role, effort, trend classification, and remediation burn-down are implemented and tested. | Weights and thresholds have not been calibrated against independently labelled real objects. Product-limit verification remains open. | 🟡 Calibration open |
| Data Agent readiness | Fifteen static rules consume supplied evidence and degrade missing inputs to `NOT_EVALUATED`. | No harness executes a corpus against a real agent; behavioural accuracy, refusal, latency, and persona isolation are therefore not measured by this repository. | 🟡 Static only |
| Fabric publication | Notebook, Data Pipeline, Lakehouse, Gold Delta marts, Direct Lake semantic model/report, run summary, trends, burn-down, and CI exit gates exist. The model/report synthetic self-assessment gate is executable. | The pipeline is schedulable, but no versioned schedule/recurrence artifact or unattended monthly-run evidence exists. “Scheduled” and “unattended” are not yet delivered claims. | 🟡 Schedulable |
| Re-measurement | Comparable-run trends, automatic baseline selection, coverage-loss classification, and remediation-state comparison are implemented. | A repeatable operational cadence, ruleset-compatible baseline policy, and recorded remediation/re-measure cycle are not yet proven end to end. | 🟡 Mechanism delivered |

### Verified Repository Baseline

At this review the documentation gate reported:

- ruleset `2026.09.1`, **65 rules** across five object types — tenant 12, workspace 11,
  semantic model 17, report 10, Data Agent 15;
- **379** passing unit tests, **1 skipped by design on Windows** —
  `tests.test_evidence_sinks` cannot create a filename containing a control character
  on NTFS, so the `-z` quoting proof skips rather than passing vacuously;
- clean generated rule documentation, internal links, and synthetic self-assessment gate;
- `python scripts/check_agent_ownership.py` exit 0 — **26** modules under `fabric_iq/`
  and `scripts/` claimed exactly once, and the **7** documents and skills asserting a
  privacy, identity, retention or collection-capability claim — or read by a model as
  instruction — each claimed by exactly one agent through an explicit `REQUIRED_DOCS`
  map. The seventh is [`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md), owned by
  `@collector`;
- `python scripts/check_evidence_sinks.py` exit 0 — **62 writer destinations** and
  documented output examples each resolve to a committed `.gitignore` rule, all **102
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
  through a collector. The tracked-file figure rises to 103 when the currently untracked
  API reality matrix is committed; the destination figure will not move with it, because
  the `artifacts/live` example it carries is already registered here.

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
artifact. Since 2026-09-24 a second, sharper anchor exists:
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

### Sprint 5.1 — Close the API Reality Matrix (3–5 days) — 🟥 **OPEN**, next actionable sprint

**Status: not cleared.** The 2026-09-24 exploratory read did **not** satisfy this sprint,
and no later sprint may treat it as though it had. Two stated prerequisites did not
happen: `@security` did not review scopes and retention *before* the read, and the reads
were issued under a delegated interactive identity holding the operator's full write
privileges rather than a **read-only service principal**. What is still required is a
**re-run under a service principal whose scopes and evidence expiry `@security` approves
first**. Until that exists, every availability classification in the matrix is
provisional, however plausible it looks.

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
   TEN-004, TEN-006, WKS-001 and WKS-010, **all six blocking**, verified against
   `python assess.py --list-rules` at ruleset `2026.09.1`.
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
   inputs demonstrably remain `NOT_EVALUATED`. **Open.** A provisional classification
   exists in [`API_REALITY_MATRIX.md`](API_REALITY_MATRIX.md), but it was obtained
   through a delegated over-privileged identity without prior scope approval and over two
   surfaces only, so it does not satisfy this criterion. Closing it requires the
   Sprint 5.1 re-run under an approved read-only service principal, with the identity
   that obtained each classification recorded alongside it.
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

## Sequencing and Release Policy

`5.0 evidence-sink hygiene ✅ → 5.0.1 standalone operability ✅ → (2026-09-24 exploratory
read — knowledge only, clears no gate) → 5.1 API proof (next, open)
→ 5.2 evidence reconciliation → 5.3 facts/calibration → 5.4 agent proof
→ 5.5 operational re-measurement`

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

## Per-Change Quality Gate

```powershell
python assess.py --list-rules
python scripts/build_rules_doc.py --check
python scripts/check_agent_ownership.py
python scripts/check_evidence_sinks.py
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
tracked-file shadowing, and tracked identifiers; `tests.test_skill_drift` covers the
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
