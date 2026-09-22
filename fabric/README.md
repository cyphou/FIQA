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
