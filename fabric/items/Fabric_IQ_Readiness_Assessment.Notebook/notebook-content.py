# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {}
# META   }
# META }

# MARKDOWN ********************

# # Fabric IQ Readiness Assessment
#
# Scores a Power BI / Fabric tenant for Fabric IQ and agentic readiness and publishes the
# result into this Lakehouse.
#
# **This notebook is strictly read-only against the assessed tenant.** It calls admin
# Scanner and Fabric read APIs only, and writes exclusively into its own Lakehouse.
#
# Three results are produced per object and are never merged:
#
# | Result | Question |
# |---|---|
# | Eligibility | Does anything make this structurally impossible? |
# | Score (0-100) | How well prepared is it? |
# | Confidence | How much could we actually observe? |
#
# Outputs:
#
# * `Files/readiness/bronze|silver|gold/**` - raw evidence, normalized inventory, marts
# * Delta tables `Mart*` - the Gold marts, ready for a governance semantic model
# * `Files/readiness/reports/<run_id>_readiness.html` - the human report

# PARAMETERS CELL ********************

# Entra tenant ID of the estate being assessed. Required.
tenant_id = ""

# Folder on this Lakehouse holding the fabric_iq package uploaded by deploy.py.
library_path = "/lakehouse/default/Files/lib"

# Medallion root inside this Lakehouse.
readiness_root = "/lakehouse/default/Files/readiness"

# Run identifier; empty means "derive a UTC timestamp".
run_id = ""

# Only scan workspaces modified in the last N days (1-30).
modified_since_days = 7

# Read workspace role assignments (getArtifactUsers). Reads named identities.
# Set to False to stay anonymous, at the cost of leaving the permission rules unevaluated.
include_artifact_users = True

# Run the preceptorship quality loop over the assessment.
run_review = True

# Publish the Gold marts as Delta tables.
publish_delta = True

# How Delta tables are published for the DirectLake report.
# "overwrite" keeps the report focused on the latest run (recommended).
# "append" keeps run history in the Delta tables for trend/reporting experiments.
delta_publish_mode = "overwrite"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import os
import sys
from datetime import datetime, timezone

if not tenant_id:
    raise ValueError("tenant_id is required; set it on the notebook activity or in the parameters cell")

if library_path not in sys.path:
    sys.path.insert(0, library_path)

import fabric_iq
from fabric_iq import RULESET_VERSION
from fabric_iq.collectors import FabricApiCollector, FabricApiConfig, FabricHttpTransport
from fabric_iq.lakehouse import GOLD, GOLD_SCHEMAS, GOLD_TABLES, LakehouseWriter
from fabric_iq.preceptor import PreceptorLoop
from fabric_iq.remediation import build_backlog
from fabric_iq.reporting import to_console, to_html
from fabric_iq.scoring import assess

run_id = run_id or datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
print(f"fabric-iq-readiness {fabric_iq.__version__} (ruleset {RULESET_VERSION})")
print(f"run_id={run_id} tenant_id={tenant_id}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Collect
#
# The token comes from the identity running the notebook. That identity needs
# **Fabric administrator** (or `Tenant.Read.All`) for the Scanner API, otherwise the
# collection degrades gracefully and the affected rules stay `NOT_EVALUATED` rather
# than silently passing.

# CELL ********************

import notebookutils  # noqa: F401  (Fabric runtime built-in)


def token_provider() -> str:
    return notebookutils.credentials.getToken("pbi")


collection = FabricApiCollector(
    FabricApiConfig(
        tenant_id=tenant_id,
        modified_since_days=int(modified_since_days),
        include_artifact_users=bool(include_artifact_users),
    ),
    FabricHttpTransport(token_provider),
).collect()

inventory = collection.inventory
print(f"mode={collection.mode}")
for section, rows in inventory.items():
    print(f"  {section}: {len(rows) if isinstance(rows, list) else 1}")
if collection.errors:
    print(f"collection errors: {len(collection.errors)}")
    for err in collection.errors[:10]:
        print(f"  - {err}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Score and review

# CELL ********************

run = assess(inventory, run_id=run_id, collector_mode=collection.mode)
backlog = build_backlog(run)
review = PreceptorLoop().run(run) if run_review else None

print(to_console(run, backlog, review))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Persist the medallion layers

# CELL ********************

written = LakehouseWriter(root=readiness_root, run_id=run_id).write_run(
    run,
    backlog,
    inventory=inventory,
    bronze=collection.bronze,
)

reports_dir = os.path.join(readiness_root, "reports")
os.makedirs(reports_dir, exist_ok=True)
run.to_json(os.path.join(reports_dir, f"{run_id}_assessment.json"))
backlog.to_json(os.path.join(reports_dir, f"{run_id}_backlog.json"))
backlog.to_csv(os.path.join(reports_dir, f"{run_id}_backlog.csv"))
if review is not None:
    review.to_json(os.path.join(reports_dir, f"{run_id}_review.json"))
to_html(run, backlog, review, os.path.join(reports_dir, f"{run_id}_readiness.html"))

print(f"written to {readiness_root}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Publish the Gold marts as Delta tables
#
# By default this step overwrites the Delta tables with the current run so the
# DirectLake report shows one clear, current readiness snapshot. The medallion
# files under `Files/readiness/gold/**` still keep each run as a separate JSONL
# file. Set `delta_publish_mode = "append"` only when you intentionally want the
# DirectLake tables themselves to keep run history for trend experiments.
#
# A mart can legitimately have zero rows for a run (a clean tenant has no blocking
# findings, a fresh scan may find no scanned objects yet). Reading an empty NDJSON
# file back with schema inference yields a DataFrame with *no columns*, which used to
# make this step skip the table entirely -- leaving it absent from the Lakehouse and
# breaking the Direct Lake report with "Invalid object name" the moment a visual
# queried it. Every table now always gets `saveAsTable`'d, using the explicit,
# typed schema in `GOLD_SCHEMAS` whenever the read is empty or fails, so it exists
# (with 0 rows if that's genuinely the case) after every run.

# CELL ********************

from pyspark.sql.types import (  # noqa: E402  (Fabric runtime built-in)
    BooleanType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

_SPARK_TYPES = {
    "string": StringType(),
    "double": DoubleType(),
    "long": LongType(),
    "boolean": BooleanType(),
}


def _empty_gold_frame(table: str):
    fields = [StructField(name, _SPARK_TYPES[dtype], True) for name, dtype in GOLD_SCHEMAS[table]]
    return spark.createDataFrame([], StructType(fields))  # noqa: F821  (Fabric runtime built-in)


if publish_delta:
    if delta_publish_mode not in {"overwrite", "append"}:
        raise ValueError("delta_publish_mode must be 'overwrite' or 'append'")
    relative_gold = f"Files/readiness/{GOLD}"
    for table in GOLD_TABLES:
        source = f"{relative_gold}/{table}/{run_id}.jsonl"
        frame = None
        try:
            frame = spark.read.json(source)  # noqa: F821  (Fabric runtime built-in)
        except Exception as exc:  # pragma: no cover - runtime-only path
            print(f"  {table}: read failed ({type(exc).__name__}: {exc}); publishing empty table")
        if frame is None or not frame.columns:
            frame = _empty_gold_frame(table)
        row_count = frame.count()
        writer = frame.write.format("delta").mode(delta_publish_mode)
        if delta_publish_mode == "overwrite":
            writer = writer.option("overwriteSchema", "true")
        else:
            writer = writer.option("mergeSchema", "true")
        writer.saveAsTable(table)
        print(f"  {table}: {delta_publish_mode} {row_count} row(s)")
else:
    print("publish_delta is False; Delta tables were not refreshed")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 5. Exit value
#
# The pipeline reads this to decide whether to alert. Blocking findings are walls, not
# quality issues: report them before any score.

# CELL ********************

import json

tenant_cards = [c for c in run.scorecards if c.object_type.value == "tenant"]
tenant_card = tenant_cards[0] if tenant_cards else None

summary = {
    "run_id": run_id,
    "tenant_id": tenant_id,
    "ruleset_version": RULESET_VERSION,
    "objects_assessed": len(run.scorecards),
    "blocking_findings": len(run.blocking_findings),
    "backlog_items": len(backlog.items),
    "tenant_score": round(tenant_card.score, 2) if tenant_card else None,
    "tenant_status": tenant_card.status.value if tenant_card else None,
    "tenant_eligible": tenant_card.eligible if tenant_card else None,
    "tenant_confidence": round(tenant_card.confidence, 4) if tenant_card else None,
    "review_verdict": review.verdict if review is not None else None,
    "review_approved": review.approved if review is not None else None,
    "collection_errors": len(collection.errors),
}
print(json.dumps(summary, indent=2))
notebookutils.notebook.exit(json.dumps(summary))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
