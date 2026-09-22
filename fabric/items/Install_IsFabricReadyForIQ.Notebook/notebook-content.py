# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # Install IsFabricReadyForIQ
#
# One-time installer. Run this notebook once, in the workspace where you want the
# **Fabric IQ Readiness** solution to live.
#
# It does exactly two things:
#
# 1. Downloads the public source of **IsFabricReadyForIQ** from
#    `https://github.com/cyphou/FIQA` over plain, unauthenticated HTTPS.
# 2. Deploys five items into **this workspace**, using **your own** delegated
#    Fabric identity (whoever is running this notebook) via
#    `notebookutils.credentials.getToken`:
#
#    | Item | Purpose |
#    |---|---|
#    | Lakehouse | Bronze / Silver / Gold store for assessment runs |
#    | Notebook | The read-only assessment engine |
#    | Data Pipeline | Orchestrates a scheduled assessment run |
#    | Semantic model (DirectLake) | Scores, findings, backlog -- no import, no refresh needed |
#    | Report | The readiness dashboard, bound to the model above |
#
# ## What this notebook never does
#
# * It never asks for, stores, or transmits a client secret, connection
#   string, or personal access token. Deployment tokens are acquired via
#   `notebookutils.credentials.getToken` and live in memory only, for the
#   duration of this run.
# * It never sends your tenant ID, workspace ID, or any tenant data to
#   GitHub or anywhere else outside Fabric -- the GitHub call is a plain,
#   anonymous file download; everything downloaded is public source code.
# * It never modifies the tenant you later assess. The `tenant_id` you set on
#   the deployed assessment notebook/pipeline is only ever *read* via Fabric
#   admin/Scanner APIs.
#
# Re-running this notebook is safe: existing items are updated in place
# (matched by display name), not duplicated.

# PARAMETERS CELL ********************

# GitHub repository holding the IsFabricReadyForIQ source, as "<owner>/<repo>".
github_repo = "cyphou/FIQA"

# Branch, tag, or commit SHA to install from.
github_ref = "main"

# Leave empty to deploy into the workspace this notebook runs in.
workspace_id = ""

# Optional: pre-fill the assessment notebook/pipeline's tenant_id parameter so
# you don't have to set it by hand after install. Leave empty and set it per
# run instead -- nothing here is required to be a real tenant.
default_tenant_id = ""

# Display names for the deployed items. Change these if you're installing more
# than one copy of the solution side by side in the same workspace.
lakehouse_name = "FabricIQReadiness"
notebook_name = "Fabric_IQ_Readiness_Assessment"
pipeline_name = "Fabric_IQ_Readiness_Orchestration"
semantic_model_name = "IsFabricReadyForIQ"
report_name = "IsFabricReadyForIQ"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Resolve the target workspace before doing anything else, so the summary at
# the end of this notebook always shows exactly where the solution landed.
import notebookutils  # noqa: F401  (Fabric-provided, not pip-installable)

if not workspace_id:
    workspace_id = notebookutils.runtime.context["currentWorkspaceId"]

print(f"Target workspace: {workspace_id}")
print(f"Source:            https://github.com/{github_repo} @ {github_ref}")

# CELL ********************

# Fetch the source as a zip archive over plain HTTPS. Public GitHub repos serve
# any branch, tag, or commit SHA this way -- no token, no auth, nothing to
# configure. Everything lands in a throw-away temp directory that is removed
# again once deployment finishes, further down.
import os
import tempfile
import urllib.request
import zipfile

install_root = tempfile.mkdtemp(prefix="fiqa_install_")
archive_path = os.path.join(install_root, "source.zip")
archive_url = f"https://github.com/{github_repo}/archive/{github_ref}.zip"

urllib.request.urlretrieve(archive_url, archive_path)  # noqa: S310 (fixed https:// GitHub URL)
with zipfile.ZipFile(archive_path) as archive:
    archive.extractall(install_root)
os.remove(archive_path)

# GitHub zips a repo under a single "<repo>-<ref>" folder -- find it.
extracted = [
    entry
    for entry in os.listdir(install_root)
    if os.path.isdir(os.path.join(install_root, entry))
]
if len(extracted) != 1:
    raise RuntimeError(f"Unexpected archive layout under {install_root}: {extracted}")
source_root = os.path.join(install_root, extracted[0])
print(f"Fetched source to {source_root}")

# CELL ********************

# Import the deployment logic straight out of the checkout we just fetched --
# nothing to pip install, the solution is stdlib-only.
import sys

if source_root not in sys.path:
    sys.path.insert(0, source_root)

from fabric_iq.deployment import DeploymentConfig, FabricRestClient, deploy  # noqa: E402
from fabric_iq.errors import DeploymentError  # noqa: E402

# CELL ********************

# Delegated auth only: each call below asks Fabric for a fresh token for the
# identity running this notebook. Tokens are never written to a variable that
# survives past this run, never logged, never persisted to disk or OneLake.
import json


def _fabric_token() -> str:
    return notebookutils.credentials.getToken("pbi")


def _onelake_token() -> str:
    return notebookutils.credentials.getToken("storage")


config = DeploymentConfig(
    workspace_id=workspace_id,
    lakehouse_name=lakehouse_name,
    notebook_name=notebook_name,
    pipeline_name=pipeline_name,
    semantic_model_name=semantic_model_name,
    report_name=report_name,
    default_tenant_id=default_tenant_id,
    items_root=os.path.join(source_root, "fabric", "items"),
    package_root=os.path.join(source_root, "fabric_iq"),
)

try:
    summary = deploy(config, FabricRestClient(_fabric_token), FabricRestClient(_onelake_token))
except DeploymentError as exc:
    raise RuntimeError(f"Deployment failed: {exc}") from exc
finally:
    # Nothing sensitive was ever written under source_root -- it's public
    # source code -- but remove it anyway so this run leaves no trace on the
    # node's local disk.
    import shutil

    shutil.rmtree(install_root, ignore_errors=True)

print(json.dumps(summary, indent=2))

# CELL ********************

# MARKDOWN ********************

# ## Next steps
#
# * Open **`Fabric_IQ_Readiness_Assessment`**, set its `tenant_id` parameter to
#   the tenant you want to assess, and run it -- or run
#   **`Fabric_IQ_Readiness_Orchestration`** to do the same on a schedule.
# * Once the first run publishes the Gold Delta tables, open the
#   **`IsFabricReadyForIQ`** report to see scores, findings, and the
#   remediation backlog.
# * You can re-run this installer at any time (for example after a new
#   release) to update the deployed items in place.

print(
    f"Done. Next: open '{summary['notebook']['name']}', set tenant_id, and run it "
    f"(or run the '{summary['pipeline']['name']}' pipeline)."
)
print(
    f"The '{summary['report']['name']}' report will show data once that first "
    "run publishes the Gold Delta tables."
)
