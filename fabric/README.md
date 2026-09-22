# 🚀 Deploy Fabric IQ Readiness Into A Fabric Workspace

This folder packages the whole assessment as a native Fabric solution: a Lakehouse that
stores the medallion output, a notebook that runs the assessment on Spark, and a Data
Pipeline that orchestrates and schedules it.

> **The assessment is strictly read-only against the tenant it evaluates.** It calls
> admin Scanner and Fabric read APIs only. The only writes it performs are into its own
> Lakehouse, in the workspace you deploy it to.

## 📦 What Gets Deployed

| Item | Name | Role |
|------|------|------|
| Lakehouse | `FabricIQReadiness` | Bronze / Silver / Gold medallion, HTML reports, `Mart*` Delta tables |
| Notebook | `Fabric IQ Readiness Assessment` | Collect, score, review, publish |
| Data Pipeline | `Fabric IQ Readiness Orchestration` | Run the notebook on a schedule and fail the run on blocking findings |
| Semantic Model | `IsFabricReadyForIQ` | Direct Lake model over the Gold `Mart*` Delta tables — no import, no refresh to manage |
| Report | `IsFabricReadyForIQ` | The Power BI report described below — tenant posture, workspace ranking, backlog |
| Notebook (installer) | `Install IsFabricReadyForIQ` | One-click deploy of every item above from inside Fabric — see [Installer Notebook](#-installer-notebook) |

The `fabric_iq` package itself is uploaded as plain `.py` sources to
`Files/lib` on the Lakehouse and imported through `sys.path`. There is no wheel and no
`%pip install`: the package is standard library only, so nothing needs resolving at
runtime.

> **Prefer not to run a local deploy script?** A single-notebook installer does the
> same thing from inside Fabric itself, using your own delegated identity and no
> secrets — see [`docs/INSTALL.md`](../docs/INSTALL.md).

## ✅ Prerequisites

- A Fabric workspace on an **F2+ or P1+ capacity**. A Pro workspace cannot host this.
- **Contributor or above** on that workspace, to create items.
- **Fabric Administrator** (or a service principal allowed to call admin APIs) for the
  identity that *runs* the notebook — the Scanner API is an admin API. Without it the
  collection returns nothing and every object lands on `NOT_EVALUATED`.
- The tenant setting *Service principals can call Fabric public APIs* enabled if you run
  the pipeline under a workspace identity or service principal.

## 🚀 Deploy

The deployment needs two tokens, because Fabric items and OneLake files sit behind
different audiences.

```powershell
$env:FABRIC_TOKEN  = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$env:ONELAKE_TOKEN = az account get-access-token --resource "https://storage.azure.com" --query accessToken -o tsv

python fabric\deploy.py `
  --workspace-id <workspace-guid> `
  --tenant-id <entra-tenant-guid>
```

`--tenant-id` is optional; it only pre-fills the default parameter value on the notebook
and the pipeline. You can always override it per run.

The script is **idempotent**: it looks each item up by display name and updates its
definition instead of creating a duplicate. Re-run it to ship a new version of the
package or the rules.

Useful flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--lakehouse-name` | `FabricIQReadiness` | Rename the Lakehouse |
| `--notebook-name` | `Fabric IQ Readiness Assessment` | Rename the notebook |
| `--pipeline-name` | `Fabric IQ Readiness Orchestration` | Rename the pipeline |
| `--token-env` | `FABRIC_TOKEN` | Environment variable holding the Fabric token |
| `--onelake-token-env` | `ONELAKE_TOKEN` | Environment variable holding the OneLake token |

## ▶️ Run

### From the pipeline

Open **Fabric IQ Readiness Orchestration** and run it. Parameters:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `tenant_id` | *(from deploy)* | Entra tenant ID of the estate being assessed. Required. |
| `modified_since_days` | `7` | Scanner window, 1–30 days |
| `include_artifact_users` | `true` | Read workspace role assignments. Reads named identities; set to `false` to stay anonymous, at the cost of leaving the permission rules unevaluated |
| `run_review` | `true` | Run the preceptorship quality loop |
| `fail_on_blocking` | `false` | Fail the pipeline run when blocking findings exist |

Schedule it from the pipeline's **Schedule** panel. Weekly is a reasonable starting
cadence: readiness debt moves slowly, and the Scanner window defaults to seven days.

`fail_on_blocking` is off by default on purpose. A first run against a real estate
almost always surfaces blocking findings, and a red pipeline on day one teaches people
to ignore it. Turn it on once you have worked the backlog down and want to defend the
line.

### From the notebook

Open **Fabric IQ Readiness Assessment**, set `tenant_id` in the parameters cell, and run
all. Same output, plus the console report inline.

## 📊 Output

Everything lands in the `FabricIQReadiness` Lakehouse.

| Path | Content |
|------|---------|
| `Files/readiness/bronze/**` | Raw evidence, hashed and timestamped — audit and replay |
| `Files/readiness/silver/**` | Normalized inventory, one table per section |
| `Files/readiness/gold/**` | The six marts as NDJSON |
| `Files/readiness/reports/<run_id>_readiness.html` | The human report |
| `Files/lib/fabric_iq/**` | The uploaded package sources |

The Gold marts are also published as Delta tables, ready to be consumed by a governance
semantic model:

- `MartTenantReadiness` — one row per tenant per run
- `MartWorkspaceReadiness` — one row per workspace per run
- `MartObjectReadiness` — one row per model, report and agent per run
- `MartBlockingFindings` — the "cannot ship" list
- `MartRemediationBacklog` — the prioritised work, by owner role
- `MartCoverageAndFreshness` — what we could actually observe

Read them in that order. **Blocking findings first** — they are walls, not quality
issues. Then coverage, so you know how much of the estate the scores actually describe.
Then the scores, always next to their confidence. The backlog last.

## 🗂️ Item Sources

```
fabric/items/
  FabricIQReadiness.Lakehouse/                    .platform
  Fabric_IQ_Readiness_Assessment.Notebook/        .platform, notebook-content.py
  Fabric_IQ_Readiness_Orchestration.DataPipeline/ .platform, pipeline-content.json
  IsFabricReadyForIQ.SemanticModel/               .platform, definition/ (TMDL)
  IsFabricReadyForIQ.Report/                      .platform, definition/ (report.json, pages)
  Install_IsFabricReadyForIQ.Notebook/            .platform, notebook-content.py
```

These are the definitions as Fabric's Git integration stores them, so the folder can
also be synced through **Workspace → Source control** instead of `deploy.py`.

Two placeholders are bound at deployment time and must stay intact in the sources:

- the notebook's `dependencies.lakehouse` metadata block, which receives the created
  Lakehouse and makes `/lakehouse/default` resolve;
- the `tenant_id = ""` line in the notebook's parameters cell, which receives
  `--tenant-id`.

Rewriting either by hand will make `deploy.py` fail loudly rather than ship a notebook
that cannot mount its own Lakehouse.

## 📈 Semantic Model & Report

`IsFabricReadyForIQ.SemanticModel` is a **Direct Lake** model over the six `Mart*` Delta
tables — there is nothing to refresh; the model reflects the Lakehouse the instant a
run finishes writing it. `IsFabricReadyForIQ.Report` is a genuine **Power BI report**
(`.pbir`/TMDL, not a static HTML export), deliberately styled after the [Fabric Capacity
Metrics](https://learn.microsoft.com/fabric/enterprise/metrics-app) and
[FUAM](https://github.com/microsoft/fabric-toolbox/tree/main/monitoring/fabric-unified-admin-monitoring)
report conventions familiar to Fabric administrators:

| Page | Answers |
|------|---------|
| Tenant Overview | Is the tenant switch configuration, capacity eligibility and scan coverage in order? |
| Workspace Ranking | Which workspaces are furthest from / closest to ready, and why? |
| Object Readiness | Score and confidence for every semantic model, report and Data Agent |
| Blocking Findings | The "cannot ship" list — walls, not quality issues |
| Remediation Backlog | The prioritised work, grouped by owner role |
| Coverage & Freshness | How much of the estate could actually be observed, and when |

Because the model is Direct Lake, the report needs no separate refresh schedule — only
the pipeline's schedule (or a manual notebook run) needs to produce a new Gold write.

## 📥 Installer Notebook

`Install_IsFabricReadyForIQ.Notebook` is the recommended way to deploy everything above
without leaving Fabric or running `deploy.py` locally — the same pattern used by FCA and
FUAM installers. Import it once into any workspace, run it, and it:

1. Clones [`cyphou/FIQA`](https://github.com/cyphou/FIQA) into a **temporary local
   checkout** using an anonymous, unauthenticated `git clone` (the repository is public
   and read-only from the notebook's point of view).
2. Deploys every item in `fabric/items/` into the current workspace via the Fabric REST
   API, using the notebook's own `notebookutils.credentials.getToken` identity — the
   same delegated identity already running the notebook, never a stored secret.
3. **Deletes the temporary checkout** before finishing, whether the run succeeds or
   fails.

**🔐 Confidentiality guarantee.** Nothing tenant-specific — no connection string,
workspace ID, tenant ID, token, or credential — is ever written to, read from, or
present in the `cyphou/FIQA` GitHub repository at any point in this flow. The GitHub
checkout supplies only the open-source item *definitions*; every value that binds those
definitions to *your* tenant (workspace ID, tenant ID, Lakehouse ID) is filled in
locally, in the temporary clone, immediately before upload, and discarded with it. See
[docs/INSTALL.md](../docs/INSTALL.md) for the full walkthrough and
[`tests/test_installer.py`](../tests/test_installer.py) for the test that enforces this
guarantee (it fails the build if a secret-shaped literal is ever committed to the
installer notebook source).

## ⚠️ Caveats

- **Field-validated**: a real deployment (`deploy.py`) followed by a direct notebook
  run against a live tenant completed successfully — items created, `Files/lib`
  uploaded, notebook job `Completed`, full Bronze/Silver/Gold output written, Gold
  Delta tables queryable, and `reports/assessment.json` read back showing a coherent
  tenant/workspace rollup. See `docs/KNOWN_LIMITATIONS.md` §1.2 for the full record.
- **Field-validated (pipeline layer)**: the pipeline's conditional failure reads
  `activity('Assess readiness').output.result.exitValue`. Two live pipeline runs
  confirmed both branches of this logic: a default run (`fail_on_blocking=false`)
  completed cleanly, proving the `IfCondition` expression evaluates without error; a
  second run (`fail_on_blocking=true`) against a tenant with a known blocking finding
  failed as expected with `errorCode: "FabricIQReadinessBlocked"` and a message
  ("... run `run_20260921T140923Z` carries 7 blocking finding(s) ...") built from the
  `run_id` and `blocking_findings` fields extracted from the same `exitValue` JSON. This
  confirms `fail_on_blocking` is safe to gate a CI/CD job on. See
  `docs/KNOWN_LIMITATIONS.md` §1.2 for the full record.
- The notebook acquires its Scanner token through `notebookutils.credentials.getToken`.
  This path was implicitly exercised by the successful live run above (Scanner-backed
  workspace/semantic-model evidence was collected). If your tenant restricts that path,
  run the assessment locally with `assess.py --live` instead and copy the output into
  the Lakehouse.
