# Identity, Scopes and Retention

Documentation owner: **@readme**, who reconciles every claim below against the code.
Reviewed by **@security**, which audits privacy, scopes and retention but owns no file by
design — a reviewer who can edit what it reviews eventually reviews its own edits.
`python scripts/check_agent_ownership.py` enforces that this document has exactly one
accountable owner.

This document is the Sprint 1.4 deliverable required by
[`ROADMAP.md`](./ROADMAP.md) Phase 1: *"a written scope and retention decision; no write
scope anywhere; the privacy audit passes on a real run's artifacts."*

It answers three questions: **who runs this tool, what can they touch, and what happens
to the evidence afterwards.**

---

## 1. Identity — who runs the collector

The live collector (`fabric_iq/collectors/fabric_api.py`) authenticates with a bearer
token obtained from an injected `TokenProvider` callable. The tool never requests,
caches, or refreshes a token itself — that responsibility is deliberately left to the
caller (an MSAL confidential-client flow, an Azure CLI credential, a managed identity,
etc.), so the collector's code surface never holds a client secret.

**Recommended identity:** a dedicated Entra service principal (or the admin API service
principal referenced by rule `TEN-007`), not a named human admin account. This gives:

- An auditable, revocable identity distinct from any person's credentials.
- A principal that can be bound to a single security group scoped to Fabric admin read
  APIs, rather than inheriting a human admin's full privilege set.
- Evidence rows (`BronzeRecord.identity`) that mean something in a real deployment,
  instead of resolving to "whoever happened to run the script."

## 2. Scopes — what the identity is allowed to touch

### 2.1 Required read scopes

The collector only ever calls the endpoints below. Every one of them is a Fabric/Power BI
**admin read** API; none accepts a body that mutates tenant, workspace, or item state.

| Endpoint | Method | Purpose |
|---|---|---|
| `/admin/tenantsettings` | GET | Tenant switches (Copilot, Fabric, cross-geo, sensitivity labels) |
| `/admin/groups` | GET | Workspace inventory (paginated with `$top`/`$skip`) |
| `/admin/capacities` | GET | Capacity SKU, state, region |
| `/admin/workspaces/getInfo` | **POST** | Scanner API's async metadata scan — the one allow-listed POST (see §2.2) |
| `/admin/workspaces/scanStatus/{id}` | GET | Poll an in-flight Scanner run |
| `/admin/workspaces/scanResult/{id}` | GET | Retrieve the completed Scanner payload |

The corresponding Entra application permissions are the standard Power BI Admin API
read scopes: `Tenant.Read.All` (tenant settings, capacities, groups) and
`Workspace.Read.All` (Scanner API). No `Tenant.ReadWrite.All`, `Workspace.ReadWrite.All`,
`Capacity.ReadWrite.All`, or any Fabric item-level write permission (`Item.ReadWrite.All`,
`Item.Execute.All`, etc.) is ever requested. If a deployment's app registration has been
granted broader scopes than this table for unrelated reasons, that is a scope-minimality
finding against the app registration, not against this tool — the code path never
exercises anything beyond the six calls above.

### 2.2 Why exactly one POST is allowed, and why it is still read-only

`FabricHttpTransport._validate_request` (`fabric_iq/collectors/fabric_api.py`) rejects
every HTTP method except `GET` and `POST`, and further rejects any `POST` whose path does
not end with an entry in `READ_ONLY_SCANNER_POSTS` (today: only
`workspaces/getInfo`). This is not a convention the caller must remember to honour — it
is enforced in the transport itself, before a request is ever sent:

```python
READ_ONLY_SCANNER_POSTS = frozenset({"workspaces/getInfo"})

@staticmethod
def _validate_request(method: str, url: str, body: dict[str, Any] | None) -> None:
    if method not in {"GET", "POST"}:
        raise CollectionError(f"read-only transport rejects {method}")
    if method == "POST":
        path = urlsplit(url).path.rstrip("/")
        if body is None or not any(path.endswith(allowed) for allowed in READ_ONLY_SCANNER_POSTS):
            raise CollectionError(f"read-only transport rejects POST endpoint: {url}")
```

`workspaces/getInfo` is a `POST` only because the Scanner API's design requires POSTing
a list of workspace IDs to *start* an asynchronous read job — the verb is an artifact of
the Microsoft API shape, not a mutation. The job itself only ever produces a metadata
snapshot (tables, columns, measures, RLS roles, Data Agent definitions, etc.); it changes
nothing in the tenant. `PUT`, `PATCH`, `DELETE`, and every other `POST` path
(provisioning, refresh triggers, permission changes, item creation) are rejected before
a socket is ever opened.

This is exercised by `test_rejects_writes_and_non_scanner_post` in
`tests/test_live_collection.py`, which asserts that a `PUT`, an unlisted `POST`, and a
`GET` carrying a body are all rejected with `CollectionError` — i.e. the guard is
tested at the transport layer, not only documented.

### 2.3 Least-privilege checklist for a real deployment

- [ ] Create a dedicated app registration / service principal; do not reuse a human
      admin's credentials or a broadly-scoped automation identity.
- [ ] Grant only `Tenant.Read.All` and `Workspace.Read.All` (or the tenant's admin-API
      equivalent group membership for the Scanner API).
- [ ] Do **not** grant any `ReadWrite`, `Execute`, or item-level Fabric permission.
- [ ] Bind the service principal to a named Entra security group (per `TEN-007`), not the
      whole organisation, so it can be audited and revoked independently of other admin
      tooling.
- [ ] Store the client secret / certificate outside this repository and outside any
      collected artifact (see §3.4).

## 3. Retention — what happens to the evidence

### 3.1 What gets persisted

Every upstream call produces one immutable `BronzeRecord`
(`fabric_iq/collectors/base.py`): `endpoint`, `collected_at`, `status_code`,
`duration_ms`, `correlation_id`, `identity`, `payload`, `schema_version`. These are the
Bronze layer described in [`ARCHITECTURE.md`](./ARCHITECTURE.md); Silver (normalised
inventory) and Gold (scored rollups, remediation backlog) are derived from them.

A run writes to **five** destinations, and each one is opt-in except `--out`. Naming only
the medallion output would understate the footprint, so every sink is listed here with
what it actually contains, verified against the writers:

| Flag | Destination on disk | What lands there | Written by |
|---|---|---|---|
| `--out` (default `artifacts`) | `<out>/<run_id>_assessment.json`, `_backlog.json`, `_backlog.csv`, `_readiness.html` (unless `--no-html`), `_review.json` (with `--review`) | Scorecards and findings: object and workspace **names**, scores, eligibility, confidence, coverage, remediation text. No raw Bronze payloads. | `assess.py` via `AssessmentRun.to_json` / `RemediationBacklog` / `fabric_iq/reporting.py` |
| `--lakehouse` | `<root>/{bronze,silver,gold}/<table>/<run_id>.jsonl` — newline-delimited JSON, one row per line | Bronze: full `BronzeRecord` dicts including `identity`, `content_hash` and the raw upstream `payload`. Silver: normalised inventory sections. Gold: the nine `GOLD_TABLES` marts. | `fabric_iq/lakehouse.py::LakehouseWriter._write_ndjson` |
| `--powerbi` | `<folder>/data/Mart*.csv` (nine marts) plus `IsFabricReadyForIQ.Report/`, `.SemanticModel/`, `.pbip`, `FabricIQ_Theme.json`, a generated `README.md` | Tenant-derived CSV marts: `tenant_id` (in `MartRunSummary`), object and workspace **names**, scores, blocking findings, backlog remediation text. `model.bim` additionally embeds the absolute local path of `data/`. | `fabric_iq/powerbi.py::PowerBiReportWriter.write_run` |
| `--checkpoint` | the single JSON file at the given path (plus a transient `.tmp` during an atomic replace) | `tenant_id`, the completed-call index, and the **raw Bronze records** — `identity` and unredacted API payloads, including workspace role assignments when `getArtifactUsers` is on. The most identity-dense file a run produces. | `fabric_iq/collectors/fabric_api.py::FabricApiCollector._save_checkpoint` |
| `--calibration` (default `artifacts/calibration`) | `<root>/<run_id>_calibration_worksheet.csv`, `_calibration_instructions.md`, `_calibration_key.json`; then, from `--calibration-analyse`, `_calibration_agreement.json` and `_calibration_disagreements.csv` | Worksheet: pseudonymised objects and the measured metadata behind them, no verdict of any kind. **Key: real object and workspace names, object ids, and the tool's `score`, `raw_score`, `status`, `eligible`, `confidence` and `coverage` in one row per sampled object — plus a `pseudonyms` map covering every object in the run, not only the sample. Never handed to a labeler.** Agreement and disagreements: pseudonyms, labeler ids, practitioner labels and their free-text rationales. | `fabric_iq/calibration.py::write_worksheet` / `write_report` |

The medallion writer emits newline-delimited JSON with the extension **`.jsonl`**, not
`.ndjson`. The distinction matters here because the protection is a filename pattern:
`.gitignore` carries `*.jsonl` precisely because an `*.ndjson`-only rule would have left
every Bronze evidence file trackable.

The table describes the writer surfaces a CLI/operator chooses with output flags. The
scheduled Fabric-native deployment is a separate evidence surface: it writes the same
Bronze/Silver/Gold layers into the `FabricIQReadiness` Lakehouse through OneLake, and
its retention contract is documented in §3.6. That contract is additive, not a
replacement for the local `--out` / `--checkpoint` / external-store handling in
§3.1-§3.5; both surfaces can exist depending on how the tool is run.

**Ignore-rule coverage is executable, not a convention.** Every destination above,
including the documented examples in this file, must resolve to a rule in a committed
`.gitignore`; no tracked file may be shadowed by those rules; and no tracked file may
carry a real tenant GUID, UPN, email or `onmicrosoft` host:

```bash
python scripts/check_evidence_sinks.py
```

That check is a heuristic gate over the repository. It reduces — and never replaces — the
mandatory pre-push privacy audit in
[`.github/agents/shared.instructions.md`](../.github/agents/shared.instructions.md), and
it says nothing about a path outside the repository: pointing `--out`, `--lakehouse`,
`--powerbi` or `--checkpoint` at a synced folder, a network share, or a ticket attachment
moves the evidence beyond anything this repository can defend. Choosing that path
deliberately, rather than defaulting into the working tree, is the practice described in
§3.5.

### 3.1.1 Git-ignored is not share-safe

An ignore rule answers exactly one question: *will git offer to commit this file?* It
says nothing about every other way a file leaves a machine. Evidence sitting inside the
working tree still escapes through a zip of the repository folder, a shared or synced
directory, a backup sweep, or an editor that indexes the whole workspace — none of which
consult `.gitignore`.

The **HTML readiness report is the artifact most likely to escape**, precisely because it
is the one designed to be shown: it is self-contained, it opens in a browser, it renders
every assessed workspace by name, and it is therefore the file an operator is most
tempted to forward. A Bronze `.jsonl` gets archived; a presentation-ready report gets
sent.

Two consequences, both practice rather than preference:

- `artifacts/` inside this checkout is for **synthetic output only** — the sample tenant,
  the self-assessment fixture, a local test run. Nothing collected from a real tenant
  belongs there, ignored or not.
- Live evidence is written to the external store in §3.5 at the moment it is produced,
  not moved there afterwards. A file that never entered the working tree cannot be
  swept up by anything that reads the working tree.

### 3.1.2 The calibration worksheet and its key have opposite handling rules

`--calibration` is the only sink designed to leave the operator's hands. Everything else
a run writes is either an aggregated mart or a report for an internal audience; the
calibration worksheet exists to be given to an outside practitioner, so the folder it
lands in contains one file that is meant to travel and one that must never travel with
it.

- **The worksheet, the instruction sheet and the key sit side by side, deliberately.**
  `write_worksheet` puts all three in the same git-ignored folder so that "hand over
  exactly one of these" is a decision somebody makes rather than a default. The failure
  mode this creates is obvious and has to be named: a reader who does not know the
  difference zips the folder and sends it. **Send the worksheet CSV and the instruction
  sheet. Never the key.**
- **The key is the re-identification map and the verdict in one file.** Per sampled
  object it carries the real `object_name` and `object_id` beside the tool's `score`,
  `raw_score`, `status`, `eligible`, `confidence` and `coverage`; its `pseudonyms` block
  additionally maps **every** object in the run — not only the 20–30 sampled ones — back
  to its real name and id, because a sampled child has to be able to name its parent
  without either name appearing on the worksheet. That makes it the most identifying
  artifact this tool produces after the `--checkpoint` file: names joined to verdicts,
  for the whole estate.
- **Handing over the key destroys the exercise as well as the privacy boundary.** The
  point of a blinded sample is to find where a practitioner's judgement and the engine's
  arithmetic diverge, and that answer is worthless once the labeler has seen the
  arithmetic. `assert_blinded` enforces the blinding of the worksheet on every build; no
  code can enforce which file an operator attaches to an email.

**Pseudonymisation is default-on and has no opt-out — and it does not discharge the
obligation.** `build_worksheet` replaces the name and id of every assessed object with a
stable pseudonym (`SM-07`), inside the row labels *and* inside the measured-fact text,
which is how [`ROADMAP.md`](./ROADMAP.md)'s risk row — *"Calibration sample contains
customer data → De-identify, retain outside git, and obtain Security approval before
use"* — is partly met. Only partly, for two reasons:

- The substitution covers the names and ids of **assessed objects**, and skips any
  identifier shorter than three characters, since replacing those would corrupt unrelated
  text more often than it would hide anything. Tenant-authored strings that are not an
  assessed object's name — table, column, measure and RLS role names, and any description
  a rule quotes as a measured fact — remain in `observed_facts` as written. The worksheet
  is blinded against the tool's verdict; it is only partially de-identified against the
  tenant.
- De-identification is one of three requirements in that row. **Retention outside git and
  Security approval before use are the other two**, and neither is implemented by code. A
  real calibration sample is tenant-derived customer data: it belongs in the external
  evidence store of §3.5 with an expiry date agreed at authorisation (§3.3), and
  **@security** approves the exercise before a practitioner sees anything.

`--calibration` defaults to `artifacts/calibration`, **inside the working tree**, which
is exactly the placement §3.1.1 reserves for synthetic output: the sample tenant, a local
test run. A calibration drawn from a real tenant is pointed at the external store the way
every other flag is — `--calibration` accepts any absolute path, and the analysis step
writes beside the key file unless `--calibration` names a folder of its own.

**The returned worksheets and the agreement outputs carry human commentary.** A filled
worksheet contains a practitioner's free-text `rationale` for each object, and
`analyse` copies those rationales verbatim into `_calibration_agreement.json` and
`_calibration_disagreements.csv`, alongside a `labeler_id` that is taken from the
returned file's stem and is in practice a person's name. So those two files identify
**people** as well as pseudonymised objects: they are a record of what two named
practitioners said about a customer's estate, and of where they disagreed. Treat them the
way §3.2 treats any tenant-authored free text — retaining them is a decision taken at
authorisation with a named expiry, not a default. Keeping a disagreement record long
enough to review it is the whole purpose; keeping it indefinitely means keeping
attributable professional judgements about a named customer with no remaining reason to.

Note also that the returned worksheets arrive from outside — by attachment, share or
upload — which creates copies of tenant-derived material that this repository never saw
and no gate can reach. They are covered by the same expiry as the rest of the exercise,
and that includes the labeler's own copy.



`BronzeRecord.payload` is the raw upstream JSON body: tenant setting flags, workspace and
capacity metadata, and — from the Scanner's semantic-model expansion — table, column, and
measure **names and descriptions**, RLS role names, and Data Agent instructions/source
lists. It does **not** contain semantic model *data* (no row-level values are ever
queried; the Scanner API returns schema metadata, not table contents) and does not
contain end-user query logs, chat transcripts, or any Copilot/Data Agent conversation
content — no such endpoint is ever called.

The residual privacy-relevant surface is therefore: workspace/item **names**, author and
owner **display names/emails** where the Scanner API includes them, and any free-text
**descriptions** an author wrote into a model, table, column, or Data Agent — these are
metadata authored by the tenant's own staff, not third-party or customer data.

### 3.3 Retention decision

> [!WARNING]
> **A checkpoint is live evidence, not scratch.** `--checkpoint` holds the tenant id next
> to unredacted Bronze payloads (§3.1). Nothing deletes it when a run completes, because
> its whole purpose is to outlive a throttled scan. **Delete it the moment the run it
> resumes has finished** — the same working session, not "next time I tidy up".
>
> This rule has been broken in practice: a checkpoint from a live proof survived three
> days past the run it resumed, carrying a tenant identifier, dozens of UPN occurrences
> across two real domains and raw admin Bronze payloads, inside a git-ignored folder that
> everyone read as safe. It was ignored; it was not share-safe (§3.1.1). The file was
> destroyed and the practice in §3.5 exists so the next one is never written into the
> working tree at all.

- **For CLI and ad-hoc output, Bronze evidence is retained only as long as the run's
  artifact directory or caller-selected Lakehouse path is retained by the operator.**
  This tool sets no retention policy of its own for those paths and runs no scheduled
  deletion — it is the responsibility of whoever owns the filesystem, workspace or
  artifact store. The unattended `FabricIQReadiness` Lakehouse is a distinct production
  surface with the contract in §3.6; that contract does not delete local `--out`,
  `--checkpoint`, `--powerbi`, or external-store files for the operator.
- **The `--checkpoint` file outlives the run that created it.** It exists to let a
  throttled scan resume, so nothing deletes it when the run completes — and it holds the
  tenant ID next to unredacted Bronze payloads. Delete it once the run it resumes has
  finished, and treat a surviving checkpoint as live evidence, not as scratch. A
  checkpoint that no unfinished scan needs has no remaining purpose and every remaining
  risk.
- **A calibration exercise has a defined end, and its files should not outlive it.** The
  worksheet, key, agreement and disagreement files (§3.1.2) are retained until the
  exercise closes — the labels are back, the disagreements have been reviewed, and any
  resulting scoring decision has been taken by a human with its own review and regression
  test. After that the worksheet and the key have no remaining purpose and every
  remaining risk; the agreement and disagreement records may be retained deliberately, on
  a named expiry, because they are the evidence the review rested on. The instruction
  sheet emitted beside them carries the run id and seed, so it is part of the same set,
  not scratch. Nothing in the tool deletes any of these.
- **A live run gets its expiry date at authorisation, not afterwards.** The date is
  agreed when the run is approved and written into the evidence store's `README.md`
  (§3.5) before the first call is made. Deciding retention after the evidence exists
  means deciding it while looking at something useful, which is how a 30-day window
  becomes indefinite. This is **@security**'s standing recommendation, adopted here as
  practice.
- **Recommended default: align Bronze retention with the shortest useful audit window.**
  This document recommends 30–90 days as a starting point; it is an operational judgement
  made here, not a Microsoft product limit and not a figure sourced from
  [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md). Long enough to explain a score to a
  steering committee, short enough that stale evidence is not
  mistaken for a current tenant state. A Gold-layer scorecard is a point-in-time
  assessment, not a live dashboard; it should carry an explicit `collected_at` and be
  treated as expired advice past its retention window rather than being re-published.
- **Cross-geo/residency:** this tool performs no cross-region data movement of its own —
  the Lakehouse deployment path (`fabric/`) writes to the same workspace/region the
  operator chooses, and the local-artifact path writes to wherever `--out` points. If a
  tenant has cross-geo processing restrictions (`TEN-*` rules check the tenant-level
  switch), the operator is responsible for running the collector from, and persisting
  evidence into, a workspace that satisfies that constraint — the tool has no opinion on
  where it is run.

### 3.4 Optional field redaction

Because `BronzeRecord.payload` can include display names and email addresses (from
workspace/item ownership metadata returned by the Scanner API), an operator who needs to
share Bronze artifacts outside a restricted audience (e.g. attaching a scorecard to a
support ticket) should redact those fields before sharing. This tool does not redact by
default — doing so silently would make Bronze a lossy, unverifiable record, which
contradicts its purpose as "immutable proof of one upstream call." Redaction, if wanted,
belongs at export/sharing time, on a copy, never on the evidence trail itself.

### 3.5 Live evidence lives outside the repository

**Practice for every live run: no tenant-derived byte is written inside the working
tree.** Both the input and the output of a run are free-form paths, so nothing forces
evidence into the checkout — `--inventory`, `--out`, `--lakehouse`, `--powerbi` and
`--checkpoint` all accept an absolute path anywhere on the machine.

#### The store

```text
C:\FabricIQ-Evidence\<date>_<purpose>\
├── README.md          # the rules below, plus the per-run expiry table
├── inventory\         # collected evidence for this run
└── report\            # --out: assessment, backlog, review, readiness.html
```

The location is chosen for two properties, not for tidiness:

- **outside the working tree**, so nothing that reads the repository folder — a zip, a
  `git add .`, a workspace-wide editor index — can reach it (§3.1.1);
- **outside any synced folder**, which is why it sits at a drive root rather than under a
  user profile directory that a consumer sync client (OneDrive and equivalents) backs up
  to cloud storage by default. Evidence that syncs has been copied to a second place
  nobody scheduled for deletion.

The store's own `README.md` carries the handling rules and a per-run expiry table, so the
retention decision travels with the evidence instead of living in someone's memory:

| Run | Purpose | Authorised | Expires | Contents |
|---|---|---|---|---|
| `<date>_<purpose>` | read-only readiness proof | `<date>` | `<date + window>` | raw collected evidence, no report retained |

**Verified, not assumed.** A full `python assess.py --inventory … --review --out …` run
was executed with both paths outside the repository: it read its inventory, scored, ran
the preceptorship review and wrote all five artifacts — including `_readiness.html` — to
the external path, with nothing created in the checkout.

```powershell
python assess.py --inventory C:\FabricIQ-Evidence\<date>_<purpose>\inventory `
                 --review --out C:\FabricIQ-Evidence\<date>_<purpose>\report
```

#### What this does and does not buy

It removes the accidental-disclosure paths that `.gitignore` never covered. It does
**not** make the evidence safe: an external folder has no ignore rule, no gate and no
`check_evidence_sinks.py` watching it — `python scripts/check_evidence_sinks.py` is blind
to every path outside the repository by construction. What protects it is the expiry date
agreed at authorisation (§3.3), the operator deleting it on that date, and the redaction
rule in §3.4 before anything is shared.

#### Reports are deleted first

Of everything a run leaves behind, the rendered readiness report is the artifact with the
highest onward-disclosure risk and usually the shortest useful life: once its findings
have been discussed, the file is a browser-ready list of real workspace names with no
remaining purpose. Delete rendered reports as soon as the conversation they supported is
over, ahead of the raw evidence they were derived from, and re-render from retained
evidence if the discussion reopens.

### 3.6 Scheduled `FabricIQReadiness` Lakehouse retention contract

Sections §3.1-§3.5 describe the local CLI and operator-selected evidence model: `--out`,
`--checkpoint`, `--powerbi`, a caller-selected `--lakehouse` path, and the external
evidence store. The scheduled Fabric-native deployment is an additional evidence
surface, not a replacement for those rules. An unattended run writes Bronze, Silver and
Gold evidence into the deployed `FabricIQReadiness` Lakehouse through OneLake, so both
the Lakehouse and local/external artifacts can exist depending on how the tool is run.

The Lakehouse contract is maximum retention, measured from durable run-lifecycle
timestamps — specifically the completed timestamp of the run that materialized the
partition, not a date inferred from `run_id`:

| Lakehouse layer | Maximum retention | Why this is the maximum |
|---|---:|---|
| Bronze raw evidence | 90 days | Raw API payloads can contain tenant-authored metadata and, when artifact-user collection (`include_artifact_users` / Scanner `getArtifactUsers`) is enabled, artifact-owner UPNs. Keep only the shortest useful audit window. |
| Silver normalized inventory | 180 days | Normalized inventory is easier to query than Bronze but remains identifying tenant inventory, so it gets a bounded comparison window rather than indefinite storage. |
| Gold readiness marts | 730 days | Longer retention supports trend and remediation comparison across compatible runs, but Gold is still tenant data: object names, findings, and nested outcome fields are not anonymous. |

Expiry means deletion from the active Lakehouse, not archival. No layer has an
indefinite default. `LakehouseWriter.write_run` now persists durable lifecycle metadata
for completed and partial runs, and the separately invoked
`LakehouseRetentionPruner.prune` applies each layer's cutoff only to manifest-declared
NDJSON partitions. A missing, malformed or incomplete manifest fails visibly for
operator action and never authorizes deletion.

Manifests are authoritative for retention classification, but they are mutable and not
tamper-evident. Anyone able to edit both a manifest and its partitions already has
destructive access to the evidence store, so storage ACLs must protect manifests to the
same standard as the evidence itself. The pruner validates manifest shape, declared
scope and root containment; it does not authenticate the truth of a retention timestamp
against an independent lifecycle source.

On platforms with directory-handle (`dir_fd`) support, such as Linux and macOS, expired
partition deletion is anchored to the already validated table directory handle, closing
the directory-swap race **@security** identified. On platforms without those portable
stdlib primitives, including Windows, a narrow residual race remains: a concurrently
running process with filesystem write access to the Lakehouse root could, in principle,
redirect a deletion by replacing a directory with a reparse point at the exact moment
between the pre-delete check and the delete call. This requires an already-present,
concurrently active, filesystem-privileged local process — a threat model far beyond
this tool's single-operator/deployment-identity execution model — and is accepted as a
stated residual risk on that platform rather than fixed, given the added complexity a
full fix would require without portable stdlib primitives. This is a deliberate,
disclosed trade-off, not an oversight.

The enforcement mechanism is implemented and tested, but it is not automatic. This
repository does not yet wire the pruner into a recurring Fabric deployment schedule or
claim a live scheduled retention cycle; that deployment-owned invocation, including its
Delta housekeeping boundary, remains follow-on operational work.

Before an unattended production schedule goes live, **@security** must review the
identity, scopes, retention windows, missing-timestamp failure path and housekeeping
design for this Lakehouse surface. That review is separate from, and does not weaken,
the local checkpoint deletion rule and external evidence-store expiry decision in §3.3
and §3.5.

## 4. No write scope anywhere — audit trail

This decision is not only documented; it is defended by tests, so a future change that
introduces a write cannot pass CI silently:

- `tests/test_live_collection.py::test_rejects_writes_and_non_scanner_post` — asserts the
  transport rejects `PUT`, an unlisted `POST` path, and a `GET` with a body.
- `fabric_iq/collectors/fabric_api.py::READ_ONLY_SCANNER_POSTS` — the single allow-listed
  POST path; any new POST endpoint added to the collector without adding it here is
  rejected by `_validate_request` rather than silently permitted.
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) §"Read-only" and
  [`ROADMAP.md`](./ROADMAP.md)'s exit-gate table both restate this as an architectural
  invariant, not merely a current default.

**Privacy audit on a real run's artifacts:** after any live scan, an operator should
confirm — by inspecting the produced Bronze/Silver/Gold artifacts in the external
evidence store (§3.5) — that (a) no
row-level model data is present (only schema metadata), (b) no Copilot/Data Agent
conversation content is present, and (c) any display-name/email fields are acceptable for
the artifact's intended audience, redacting per §3.4 if not. This is a manual check today
(no automated PII scanner exists in this project); automating it is out of scope for
Sprint 1.4 and is not currently tracked as a gap because no such scanner was promised by
the exit gate — the gate asks for a passing manual audit on a real run, which the
checklist above satisfies.
