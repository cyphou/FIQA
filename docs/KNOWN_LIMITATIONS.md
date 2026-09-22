# Known Limitations

The most important document in this repository. A readiness assessor that does not state
what it cannot see invites over-trust, and over-trust is how a tool like this causes harm.

Last reviewed: ruleset `2026.09.1`.

## 1. Live Collection Is A Foundation, Not Validated Field Coverage

`fabric_iq/collectors/fabric_api.py` includes a standard-library HTTP transport with
injected bearer-token retrieval, GET pagination, the read-only Scanner `getInfo` POST,
bounded `429` retry, Bronze response evidence, and checkpoint resume. It does not
acquire, persist, or log credentials; the CLI accepts the *name* of a token environment
variable rather than a token value.

The endpoint-to-field mappings have not yet been verified against a live tenant or every
supported SKU. In particular, this phase normalizes tenant settings and Scanner workspace,
dataset, report, and data-agent containers only when returned by the APIs. It must not be
treated as a complete tenant inventory.

**Consequence.** A live run can provide auditable partial evidence, but its unverified
fields remain `NOT_EVALUATED`. Validate API permissions, endpoint availability, and field
shapes in the target environment before presenting a result as a complete assessment.

### 1.1 What The First Live Validation Established

A first end-to-end run against a real tenant confirmed the transport, the Scanner
normaliser and the `/admin/capacities` join, and corrected three beliefs that had been
assumed rather than observed:

| Belief | Verdict after live observation |
|--------|-------------------------------|
| Scanner `relations` carries semantic-model relationships | **False.** It carries inter-artifact lineage (`dependentOnArtifactId`, `relationType`). Model relationships are not exposed there, so `relationships` stays `None` — unobserved, never empty. |
| Workspace capacity state is always readable | **Partly.** `sku` and `state` resolve through the capacity join; `throttled` is **not returned** by `/admin/capacities`, so throttling rules stay `NOT_EVALUATED`. |
| `SEM-*` coverage would be broadly evaluable | **No.** Roughly **8 of 17** `SEM-*` rules evaluate on live Scanner output. That is an honest measurement of what the API exposes, not a defect. |

Two distinctions proved load-bearing and are now encoded:

- **A present key holding `None` means "not observed"; `[]` or `""` means "observed and
  empty".** The second is an assertion, the first is a blind spot. `require()` treats a
  `None` value as missing, and collection code must use `x.get(k) or []` rather than
  `x.get(k, [])`, which would hand back `None`.
- **Missing evidence blocks a *rule*, not a *field*.** A rule whose inputs are absent
  returns `NOT_EVALUATED` as a whole; an individual absent element inside an otherwise
  observed list does not silently become a failure.

Enabling `getArtifactUsers` on the Scanner call later lifted `evidence_completeness`
from **1.90 to 2.21** on the same tenant, by making the workspace permission rules
evaluable. It remains far from the 4.0 preceptorship threshold: roughly two thirds of
findings still carry no evidence, and that gap is a collection problem, not a scoring
one.

### 1.2 The Fabric Deployment Is Field-Validated

The items under `fabric/items/` follow the documented Fabric Git-integration layout and
the Items REST definition contract, and the builders that bind them are unit-tested.
A first real deployment and notebook execution against a live tenant (workspace
`Fabric IQ Readiness`, capacity SKU `FTL4`) completed successfully end to end:

- all four items (Lakehouse, auto-generated SQL endpoint, Notebook, DataPipeline)
  deployed and the `Files/lib` library uploaded through the OneLake DFS API;
- the notebook job ran to `Completed` and wrote the full medallion output — Bronze
  evidence, Silver per-object-type NDJSON, Gold Delta tables (`Tables/mart*`,
  queryable through the SQL endpoint), and the `reports/` bundle (`assessment.json`,
  `backlog.csv`/`.json`, `review.json`, `readiness.html`);
- the produced `assessment.json` was read back and is structurally and semantically
  coherent: a tenant scorecard (score 41.14, `eligible: true`, coverage 43%) rolled up
  from 7 real workspaces, each with its own scorecards and blocking findings — including
  a correct `WKS-001` blocking finding on the deployment's own `FTL4` trial capacity,
  which is not Copilot-eligible.

One assumption from the previous review turned out to be a **false alarm caused by a
malformed verification query**, not a code defect: querying the OneLake DFS list API with
the item ID as an extra URL path segment (instead of as the leading component of the
`directory` query parameter) makes the API echo a synthetic 4-folder listing
(`Files`, `Functions`, `TableMaintenance`, `Tables`) at every level queried that way. A
correctly-formed recursive listing from the filesystem root (`directory` omitted, no
extra path segment) shows the real, non-duplicated structure. No fix was needed in
`fabric_iq/lakehouse.py` or the notebook.

The pipeline's `exitValue` wiring has since been validated directly through two live
pipeline runs (as opposed to just the notebook activity in isolation):

- **Run 1** (default parameters, `fail_on_blocking=false`): triggered via
  `POST /v1/workspaces/{ws}/items/{pipelineId}/jobs/instances?jobType=Pipeline`,
  reached `status: "Completed"` with `failureReason: null` in ~1m38s. This proves the
  `IfCondition` activity's expression —
  `@and(pipeline().parameters.fail_on_blocking, greater(int(json(string(activity('Assess
  readiness').output.result.exitValue)).blocking_findings), 0))` — evaluates without
  error against a real notebook-activity output.
- **Run 2** (`executionData.parameters = { tenant_id: "<tenant>", fail_on_blocking: true
  }`, against a tenant with a known blocking finding): reached `status: "Failed"` with
  `failureReason.errorCode: "FabricIQReadinessBlocked"` and
  `failureReason.message: "Operation on target Fail on blocking findings failed: Fabric
  IQ readiness run run_20260921T140923Z carries 7 blocking finding(s). Read
  MartBlockingFindings before discussing any score."` — confirming the nested `Fail`
  activity correctly extracts both `run_id` and `blocking_findings` from the same
  `exitValue` JSON.

Both branches of the pipeline's `exitValue`-dependent logic are therefore
field-validated. `notebookutils.credentials.getToken("pbi")` returning a token the admin
Scanner API accepts was also implicitly exercised by the successful notebook run above,
since live collection populated real Scanner-backed workspace/semantic-model evidence.

### 1.3 Quota Handling Is Proactive Throttling, Not True Concurrency Control

Sprint 1.2 closed the quota/scale gap left open after the first live validation. Three
config constants existed before any code consumed them; each has now been resolved
deliberately rather than left as dead configuration:

- **`MAX_GETINFO_CALLS_PER_HOUR` is now enforced.** `FabricApiCollector._throttle_getinfo_quota`
  tracks a rolling one-hour window of getInfo call timestamps in memory and sleeps just
  long enough for the oldest call to age out before issuing the next one, once the ceiling
  is reached. This is a **per-process, not tenant-wide** approximation: it prevents this
  run from exceeding the admin API's hourly getInfo quota on its own, but it has no
  visibility into calls made by another process (a second scheduled run, a human using the
  Fabric admin portal's own scanner, etc.) against the same tenant in the same window. A
  tenant-wide, cross-process quota tracker would require a shared, persisted call-time
  store — out of scope for a stdlib-only, read-only tool.
- **`MAX_CONCURRENT_SCANS` is intentionally unused.** Batches (each ≤
  `MAX_WORKSPACES_PER_SCAN` workspaces) are scanned **sequentially**, not concurrently.
  Concurrency would reduce wall-clock time on large tenants but adds real risk for a
  read-only auditing tool: interleaved retries, shared-mutable-state bugs in the
  checkpoint writer, and harder-to-reason-about throttling math, for a tool whose
  correctness bar is "never invent evidence." Sequential batching was kept as the
  simpler, safer default. If a future large-tenant deployment proves sequential scanning
  is a real bottleneck, concurrency should be added with its own dedicated test suite
  rather than folded into this constant silently.
- **`modified_since_days` is validated but not wired to an incremental scan.** The field
  exists on `FabricApiConfig` and is range-checked, but no code path uses it to
  filter or resume a scan by modification date. Doing so safely would require a
  persisted full-inventory store to merge incremental results into — without one, a
  "modified since" scan risks silently union-ing stale full-tenant evidence with fresh
  partial evidence, which conflicts directly with the project's "never invent evidence"
  rule. This is documented in code (see the comment above `modified_since_days` in
  `fabric_iq/collectors/fabric_api.py`) as an intentional deferral, not an oversight.
- **`ACTIVITY_RETENTION_DAYS` and `MAX_ACTIVITY_CALLS_PER_HOUR` remain unused.** No
  activity-log collector exists yet in this codebase — these constants were declared
  ahead of that future collector and have nothing to throttle or retain today. They are
  not a Sprint 1.2 gap; they are scope for a not-yet-built activity-log collector.

**Consequence.** A single run of this tool will not exceed the getInfo hourly quota on
its own, and large tenants degrade honestly (a failed batch reduces `workspaces_scanned`
and records an error, it never invents the missing workspaces) rather than either
silently succeeding or aborting the whole scan. Multi-process quota contention and
activity-log throttling remain open for future work.

## 2. Metadata Availability Is Unconfirmed

Several rules consume fields whose availability through public read-only APIs has not
been verified against a live tenant:

| Field | Consumed by | Status |
|-------|-------------|--------|
| AI data schema / Prep-for-AI selection | `SEM-008`, `SEM-009` | Unconfirmed |
| AI instructions | `SEM-010`, `SEM-011` | Unconfirmed |
| Verified answers | `SEM-012` | Unconfirmed |
| Data Agent definition and sources | `AGT-001` … `AGT-005` | Unconfirmed |
| Agent instructions | `AGT-007` | Unconfirmed |

**Consequence.** Rules reading an unavailable field will correctly return
`NOT_EVALUATED` — which is honest, but means the corresponding readiness dimension is a
blind spot rather than a measurement.

**Resolution.** Sprint 1.1 is a three-day proof of concept whose explicit purpose is to
produce a field-by-field availability table and delete or reclassify any rule that cannot
be evidenced.

## 3. Agent Quality Is Declared, Not Measured

`AGT-006` … `AGT-012` consume an `evaluation` block: accuracy, critical accuracy, persona
count, leakage incidents, refusal behaviour, latency. Today that block is **supplied as
input**. The tool does not yet execute a corpus against a live agent.

**Consequence.** An agent's behavioural score is only as trustworthy as the evaluation
that produced it. With no evaluation supplied, those rules return `NOT_EVALUATED` — they
never assume success.

**Resolution.** Phase 3 builds the evaluation harness.

## 4. The Tool Cannot Author An Evaluation Corpus

Measuring whether an agent answers correctly requires knowing what correct is. That is a
business judgement — which questions matter, which are critical, what a right answer looks
like. The tool measures a corpus; it cannot write one, and a generated corpus would
measure only its own assumptions.

## 5. Weights Are Reasoned, Not Calibrated

Dimension weights and the 85/70/50 thresholds are defensible but have not been validated
against practitioner judgement on a real estate. Sprint 2.2 measures agreement between
the tool's verdicts and independent expert labels.

**Consequence.** Relative ranking between objects is more reliable than an absolute score
at this stage. "This model is in worse shape than that one" is better supported than
"this model scores 72".

## 6. Static Readiness Is A Prediction

A perfect static score says the metadata is in good shape. It does not say the agent will
answer correctly. Only Phase 3 measurement converts the prediction into a claim. The two
are deliberately never merged into one number.

## 7. Endorsement Is Not Evidence

`Approved for Copilot` is set by the content author. It expresses intent, not verification.
No rule treats it as proof of quality. Relatedly, a **report is not individually approved
for Copilot** — the approval rides on the semantic model — so `REP-*` rules score a report
as a context and validation surface rather than as an endorsed asset.

## 8. Product Limits Age

Every hard limit encoded in the catalogue is a dated fact:

| Limit | Value | Used by |
|-------|-------|---------|
| Data sources per agent | 5 | `AGT-002` |
| Agent result surface | 25 rows × 25 columns | `AGT-013` |
| Description budget read by Copilot | 200 characters | `SEM-006`, `SEM-007` |
| AI instructions maximum | 10,000 characters | `SEM-011` |
| Capacity floor | F2+ / P1+ | `TEN-004`, `WKS-001` |
| Purview access restriction policies (KQL DB, SQL DB, Data Warehouse) | Preview at time of writing | `TEN-012` |
| Scanner `getInfo` | 500/hour, 16 concurrent, 100 workspaces/request | collector |
| Activity Events | 1 UTC day/request, 28-day retention, 200/hour | collector |

The capacity floor carries a nuance worth stating, because a live run will surface it:
a **Trial** SKU is not an eligible host, so `WKS-001` fails on a trial-backed workspace
— that is a true positive, not noise. Separately, a **Fabric Copilot capacity** (F2+/P1+)
can carry Copilot billing for usage originating in another workspace. The two facts
coexist: the workspace still needs an eligible host of its own.

Data Agents run on any eligible capacity (F2+ or P1+) with no additional floor. An
earlier revision of this catalogue asserted that capacities below F64 needed the tenant
**"Capacities can be designated as Fabric Copilot capacities"** setting explicitly
re-enabled, and the workspace's users assigned to such a capacity, before Data Agents
would function — that assertion was tested directly against a live F2-capacity tenant
and found to be false, so the corresponding rules (`TEN-011`, `WKS-011`) were removed.
The "Capacities can be designated as Fabric Copilot capacities" setting is a distinct
billing/attribution mechanism (it lets Copilot usage on one workspace bill against a
different, designated capacity); it is unrelated to whether Data Agents can run.

Finally, **Microsoft Purview data loss prevention (DLP) policies and access restriction
policies do not override effective permissions**. A Data Agent runs under the requesting
user's own permissions, so DLP/sensitivity labels reduce visibility only where a policy
exists and applies; `TEN-012` checks that this review happened, not that it is sufficient
on its own — workspace and OneLake permissions must still be tightened directly wherever
Purview does not reach. Access restriction policies for KQL Database, SQL Database and
Data Warehouse were in **preview** at the time this rule was written; Data Warehouse DLP
policies were **generally available**. Re-check current status before relying on this
table — these limits age, per the header of this section.

`RULESET_VERSION` pins what was believed true when a score was produced. **Scores are
only comparable across runs with the same ruleset version**; the trend view must refuse
to plot across incompatible versions rather than silently mixing them.

## 9. Coverage Below 50% Publishes Nothing

By design. An object we could observe only partially is reported as `NOT_EVALUATED`, not
as a low score. This will feel unhelpful the first time a large portfolio returns mostly
`NOT_EVALUATED` — that output is accurate, and the fix is better collection, not a lower
floor.

## 10. Retiring Dependencies

**Power BI Q&A** is announced for retirement in December 2026. No rule may add a new
dependency on it; existing usage in a customer estate should be flagged as technical debt
rather than scored as readiness.

## 11. Scope Boundaries

This tool will not:

- modify a tenant, under any flag, for any reason;
- decide which objects are business-critical;
- author descriptions, instructions, or evaluation corpora;
- guarantee agent behaviour from static metadata alone.
