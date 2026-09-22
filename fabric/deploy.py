"""Deploy the readiness assessor into a Fabric workspace.

    python fabric/deploy.py --workspace-id <guid> --tenant-id <guid>

Two tokens are needed, because Fabric items and OneLake files live behind different
audiences:

    $env:FABRIC_TOKEN  = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
    $env:ONELAKE_TOKEN = az account get-access-token --resource "https://storage.azure.com" --query accessToken -o tsv

This writes into *your* delivery workspace. The tenant being assessed is never modified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fabric_iq.deployment import (  # noqa: E402
    DeploymentConfig,
    FabricRestClient,
    deploy,
)
from fabric_iq.errors import AssessmentError  # noqa: E402


def _token_provider(env_var: str):
    def provider() -> str:
        token = os.environ.get(env_var, "")
        if not token:
            raise AssessmentError(f"environment variable {env_var} is empty")
        return token

    return provider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy the Fabric IQ readiness solution")
    parser.add_argument("--workspace-id", required=True, help="target Fabric workspace id")
    parser.add_argument("--tenant-id", default="", help="tenant assessed by default (optional)")
    parser.add_argument("--lakehouse-name", default="FabricIQReadiness")
    parser.add_argument("--notebook-name", default="Fabric_IQ_Readiness_Assessment")
    parser.add_argument("--pipeline-name", default="Fabric_IQ_Readiness_Orchestration")
    parser.add_argument("--semantic-model-name", default="IsFabricReadyForIQ")
    parser.add_argument("--report-name", default="IsFabricReadyForIQ")
    parser.add_argument("--token-env", default="FABRIC_TOKEN", help="env var holding the Fabric API token")
    parser.add_argument("--onelake-token-env", default="ONELAKE_TOKEN", help="env var holding the storage token")
    args = parser.parse_args(argv)

    config = DeploymentConfig(
        workspace_id=args.workspace_id,
        lakehouse_name=args.lakehouse_name,
        notebook_name=args.notebook_name,
        pipeline_name=args.pipeline_name,
        semantic_model_name=args.semantic_model_name,
        report_name=args.report_name,
        default_tenant_id=args.tenant_id,
    )

    try:
        summary = deploy(
            config,
            FabricRestClient(_token_provider(args.token_env)),
            FabricRestClient(_token_provider(args.onelake_token_env)),
        )
    except AssessmentError as exc:
        print(f"Deployment failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    print(
        f"\nRun the pipeline '{summary['pipeline']['name']}' "
        f"or open the notebook '{summary['notebook']['name']}' and supply tenant_id."
    )
    print(
        f"Report '{summary['report']['name']}' is bound to semantic model "
        f"'{summary['semantic_model']['name']}', which reads the Gold marts directly via "
        "DirectLake (SQL analytics endpoint) -- no data source credentials to configure. "
        "The tables are empty until an assessment run publishes the Gold Delta tables, so "
        "run the pipeline or notebook at least once before opening the report."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
