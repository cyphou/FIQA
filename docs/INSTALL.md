# 📦 One-Notebook Install

Like FCA (Fabric Capacity Metrics) and FUAM, this project ships a single installer
notebook. Import it once into the workspace where you want the solution to live, run
it, and it deploys everything else for you — no local Python, no `az` CLI, no service
principal, no secret of any kind.

The installer notebook lives at
[`fabric/items/Install_IsFabricReadyForIQ.Notebook/notebook-content.py`](../fabric/items/Install_IsFabricReadyForIQ.Notebook/notebook-content.py)
in the public repo [github.com/cyphou/FIQA](https://github.com/cyphou/FIQA).

## 🔍 What It Does

Exactly two things:

1. Downloads the public source of **IsFabricReadyForIQ** from `cyphou/FIQA` over plain,
   unauthenticated HTTPS (a GitHub archive `.zip`, the same URL your browser would use).
2. Deploys the five solution items into **the workspace you run it in**, using **your
   own** delegated Fabric identity:

   | Item | Purpose |
   |---|---|
   | Lakehouse | Bronze / Silver / Gold store for assessment runs |
   | Notebook | The read-only assessment engine |
   | Data Pipeline | Orchestrates a scheduled assessment run |
   | Semantic model (DirectLake) | Scores, findings, backlog — no import, no refresh |
   | Report | The readiness dashboard, bound to the model above |

Re-running the installer is safe: every item is matched by display name and updated in
place, never duplicated. Re-run it after a new release to pick up rule/report updates.

## ✅ Prerequisites

Same as a manual deploy — see [`fabric/README.md`](../fabric/README.md#prerequisites):

- A Fabric workspace on **F2+ or P1+ capacity** (a Pro workspace cannot host a
  DirectLake model here).
- **Contributor or above** on that workspace, for the identity running the installer.
- Outbound HTTPS access to `github.com` from the Fabric runtime (default in most
  tenants; some network-restricted capacities disallow it — see Troubleshooting below).

## 🚀 Steps

1. **Import the notebook.**
   In the target workspace: **New item ▸ Notebook ▸ Import notebook**, then point it at
   the raw file:
   `https://raw.githubusercontent.com/cyphou/FIQA/main/fabric/items/Install_IsFabricReadyForIQ.Notebook/notebook-content.py`
   (or download it first and import the local file — either works).
2. **Open the imported notebook** and check the parameters cell:

   | Parameter | Default | Meaning |
   |---|---|---|
   | `github_repo` | `cyphou/FIQA` | Source repo, as `<owner>/<repo>` |
   | `github_ref` | `main` | Branch, tag, or commit SHA to install from |
   | `workspace_id` | *(empty)* | Leave empty to deploy into the workspace the notebook runs in |
   | `default_tenant_id` | *(empty)* | Optional: pre-fill the assessment notebook/pipeline's `tenant_id` so you don't have to set it by hand afterwards |
   | `lakehouse_name` | `FabricIQReadiness` | |
   | `notebook_name` | `Fabric_IQ_Readiness_Assessment` | |
   | `pipeline_name` | `Fabric_IQ_Readiness_Orchestration` | |
   | `semantic_model_name` | `IsFabricReadyForIQ` | |
   | `report_name` | `IsFabricReadyForIQ` | |

   The last five let you install more than one copy side by side in the same workspace
   (for example one per environment) by giving each copy distinct names.
3. **Run all.** The notebook prints the resolved target workspace, fetches and extracts
   the source to a temp directory, imports `fabric_iq` straight out of that checkout,
   deploys the five items, and prints a JSON summary plus a "Next steps" line.
4. **Set `tenant_id` and run the assessment.** Open the deployed
   `Fabric_IQ_Readiness_Assessment` notebook (or `Fabric_IQ_Readiness_Orchestration`
   pipeline for a scheduled run), set `tenant_id` to the Entra tenant you want to
   assess, and run it. Once it publishes the Gold Delta tables, open the
   `IsFabricReadyForIQ` report to see scores, findings, and the remediation backlog.

## 🗓️ Production Schedule Contract

The installer deploys the same schedule contract described in
[`fabric/README.md`](../fabric/README.md#schedule-contract-v1): the Data Pipeline is
safe to schedule weekly by default, has `concurrency=1` to prevent overlapping runs,
and generates a fresh timestamped `run_id` for each pipeline run. Operators set the
actual recurrence in the deployed pipeline's **Schedule** panel; the repository does not
ship a tenant-specific calendar artifact.

Before enabling a recurring production schedule, make the pipeline owner/execution
identity the Sprint 5.1 `@security`-approved read-only service principal referenced in
[`ROADMAP.md`](./ROADMAP.md#sprint-51--close-the-api-reality-matrix-35-days---open-next-actionable-sprint).
Fabric documents this production path as setting a service principal as the pipeline
owner by having it update the pipeline. The delegated human identity that imports this
installer may deploy the items, but it must not be the unattended schedule identity.

For schedule-run housekeeping, keep failed or orphaned scheduler run records and
incident notes for at least 30 days or until a successful rerun has been reviewed,
whichever is later. That boundary covers only operational schedule attempts; the
Bronze/Silver/Gold evidence-retention decision remains separate. A production deployment
must also configure Fabric monitoring/alerting, or its chosen Teams/email/ITSM route, to
notify a human on pipeline failures. When `fail_on_blocking=true`, the deployed pipeline
raises `FabricIQReadinessBlocked` so the alert can distinguish a readiness gate from an
infrastructure failure without parsing notebook logs.

The Sprint 5.5 proof run is still open: the roadmap's Re-Verification Attempt records
that the previously deployed `Fabric IQ Readiness` workspace is unreachable. Do not use
this repository contract alone to claim an unattended synthetic-safe run, Sprint 5.5
completion, or Phase 5 release-gate item 8 completion.

## 🔐 Confidentiality Guarantees

This was a hard requirement for the installer and is enforced by its design, not just
its documentation:

- **No secret of any kind is ever requested, stored, or transmitted.** The only
  credentials used are two short-lived delegated tokens obtained via
  `notebookutils.credentials.getToken("pbi")` and `notebookutils.credentials.getToken("storage")`
  — the identity of whoever is running the notebook, nothing else. There is no client
  ID, client secret, connection string, or personal access token anywhere in the
  notebook or in `fabric_iq`.
- **Tokens never leave memory.** They are held only inside short-lived closures passed
  straight into `FabricRestClient`, never assigned to a variable that survives the
  deploy call, never printed, never logged, never written to disk or OneLake.
- **The GitHub call is one-way and anonymous.** It is a plain, unauthenticated HTTPS
  `GET` of a public archive URL. Nothing about your tenant — no tenant ID, workspace ID,
  or tenant data — is ever sent to GitHub or anywhere outside Fabric.
- **The temp checkout is always deleted**, even if deployment fails, via a `finally`
  block (`shutil.rmtree(install_root, ignore_errors=True)`). No trace of the downloaded
  source is left on the node's local disk after the run.
- **The installer never touches the tenant it will later assess.** It only creates
  items in the workspace it runs in. The `tenant_id` parameter it can pre-fill is stored
  as a plain notebook parameter value — it is *read* later by the assessment notebook
  via Fabric admin/Scanner APIs, never *written* anywhere by the installer itself.
- This is verified by an automated test suite
  ([`tests/test_installer.py`](../tests/test_installer.py)), which includes a regex
  guard that fails the build if any secret-shaped literal (`client_secret`,
  `access_token`, `api_key`, `connection_string`, …) is ever hardcoded into the notebook
  source.

## 🩹 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `urllib.error.URLError` fetching the archive | Outbound HTTPS to `github.com` is blocked by the capacity's network rules or a private-network Fabric gateway | Ask a tenant admin to allow-list `github.com` / `codeload.github.com`, or fall back to the manual deploy path in [`fabric/README.md`](../fabric/README.md) from a machine that does have GitHub access |
| `RuntimeError: Unexpected archive layout under ...` | The `github_ref` you set doesn't exist, or GitHub changed its archive layout | Check `github_ref` is a real branch/tag/SHA on `cyphou/FIQA`; the archive is expected to contain exactly one top-level folder |
| Deployment fails with a permissions error | The identity running the notebook lacks Contributor+ on the target workspace | Grant Contributor (or above) and re-run — the installer is idempotent |
| Report/model show no data after install | Expected — the installer only deploys empty items | Run `Fabric_IQ_Readiness_Assessment` (or the pipeline) at least once with a real `tenant_id` |

## 🛠️ Manual / Scripted Alternative

If you prefer not to import a notebook from GitHub (for example in an air-gapped
tenant), the same five items can be deployed from a local clone with `fabric/deploy.py`
— see [`fabric/README.md`](../fabric/README.md). The installer notebook is a thin,
zero-install wrapper around exactly the same `fabric_iq.deployment.deploy()` function;
both paths produce an identical result.
