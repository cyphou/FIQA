#!/usr/bin/env python3
"""Fabric IQ Readiness Assessor — command line entry point.

Examples:
    python assess.py --inventory examples/sample_tenant --out artifacts
    python assess.py --inventory examples/sample_tenant --review --fail-on-blocking
    python assess.py --inventory examples/sample_tenant --lakehouse ./lakehouse
    python assess.py --inventory examples/sample_tenant --powerbi ./powerbi_report
    FABRIC_ACCESS_TOKEN=... python assess.py --live --tenant-id tenant-id --bearer-token-env FABRIC_ACCESS_TOKEN
    python assess.py --list-rules
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from fabric_iq import RULESET_VERSION, __version__
from fabric_iq.collectors import FabricApiCollector, FabricApiConfig, FabricHttpTransport, OfflineCollector
from fabric_iq.errors import AssessmentError
from fabric_iq.lakehouse import LakehouseWriter
from fabric_iq.models import ObjectType
from fabric_iq.powerbi import PowerBiReportWriter
from fabric_iq.preceptor import PreceptorLoop
from fabric_iq.remediation import build_backlog
from fabric_iq.reporting import to_console, to_html
from fabric_iq.rules import registry
from fabric_iq.scoring import assess


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fabric-iq-readiness",
        description="Score a Power BI / Fabric tenant for Fabric IQ and agentic readiness.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--inventory", help="Path to a normalized inventory JSON file or fixture folder")
    source.add_argument("--live", action="store_true", help="Collect a live tenant using read-only APIs")
    parser.add_argument("--tenant-id", help="Entra tenant ID required by --live")
    parser.add_argument(
        "--bearer-token-env",
        help="Name of the environment variable that supplies a live bearer token; never pass tokens on the command line",
    )
    parser.add_argument("--checkpoint", help="Path for resumable live-collection checkpoint data")
    parser.add_argument(
        "--no-artifact-users",
        action="store_true",
        help=(
            "Do not request workspace role assignments during a live scan. "
            "Avoids reading named identities, at the cost of leaving the workspace "
            "permission rules unevaluated"
        ),
    )
    parser.add_argument("--out", default="artifacts", help="Output folder for reports (default: artifacts)")
    parser.add_argument("--run-id", help="Run identifier (default: UTC timestamp)")
    parser.add_argument("--lakehouse", help="Root folder for the Bronze/Silver/Gold medallion output")
    parser.add_argument("--powerbi", help="Root folder for a generated Power BI (.pbip) report project")
    parser.add_argument("--review", action="store_true", help="Run the preceptorship quality loop")
    parser.add_argument(
        "--max-cycles", type=int, default=3, help="Maximum preceptorship cycles (default: 3)"
    )
    parser.add_argument(
        "--fail-on-blocking",
        action="store_true",
        help="Exit with code 2 when any object carries a blocking finding",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Exit with code 3 when the preceptorship loop escalates",
    )
    parser.add_argument("--no-html", action="store_true", help="Skip the HTML report")
    parser.add_argument("--quiet", action="store_true", help="Suppress the console summary")
    parser.add_argument("--list-rules", action="store_true", help="Print the rule catalogue and exit")
    parser.add_argument("--version", action="store_true", help="Print versions and exit")
    return parser


def list_rules() -> int:
    print(f"Ruleset {RULESET_VERSION} — {len(registry)} rules\n")
    for object_type in ObjectType:
        rules = registry.for_type(object_type)
        if not rules:
            continue
        print(f"{object_type.value.upper()} ({len(rules)})")
        for rule in sorted(rules, key=lambda r: r.id):
            print(
                f"  {rule.id:<8} [{rule.severity.value:<8}] "
                f"{rule.dimension.value:<20} {rule.title}"
            )
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.version:
        print(f"fabric-iq-readiness {__version__} (ruleset {RULESET_VERSION})")
        return 0
    if args.list_rules:
        return list_rules()
    if not args.inventory and not args.live:
        print("error: --inventory or --live is required (or use --list-rules / --version)", file=sys.stderr)
        return 1
    if args.live and (not args.tenant_id or not args.bearer_token_env):
        print("error: --live requires --tenant-id and --bearer-token-env", file=sys.stderr)
        return 1

    run_id = args.run_id or datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")

    try:
        if args.live:
            token_name = args.bearer_token_env

            def token_provider() -> str:
                return os.environ.get(token_name, "")

            collection = FabricApiCollector(
                FabricApiConfig(
                    tenant_id=args.tenant_id,
                    checkpoint_path=args.checkpoint,
                    include_artifact_users=not args.no_artifact_users,
                ),
                FabricHttpTransport(token_provider),
            ).collect()
        else:
            collection = OfflineCollector(args.inventory).collect()
        run = assess(collection.inventory, run_id=run_id, collector_mode=collection.mode)
        backlog = build_backlog(run)

        review = None
        if args.review:
            review = PreceptorLoop().run(run, max_cycles=args.max_cycles)

        os.makedirs(args.out, exist_ok=True)
        run.to_json(os.path.join(args.out, f"{run_id}_assessment.json"))
        backlog.to_json(os.path.join(args.out, f"{run_id}_backlog.json"))
        backlog.to_csv(os.path.join(args.out, f"{run_id}_backlog.csv"))
        if review is not None:
            review.to_json(os.path.join(args.out, f"{run_id}_review.json"))
        if not args.no_html:
            to_html(run, backlog, review, os.path.join(args.out, f"{run_id}_readiness.html"))

        if args.lakehouse:
            LakehouseWriter(root=args.lakehouse, run_id=run_id).write_run(
                run,
                backlog,
                inventory=collection.inventory,
                bronze=collection.bronze,
            )

        if args.powerbi:
            PowerBiReportWriter(root=args.powerbi).write_run(run, backlog)

        if not args.quiet:
            print(to_console(run, backlog, review))
        print(f"Artifacts written to {os.path.abspath(args.out)}")

    except AssessmentError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.fail_on_blocking and run.blocking_findings:
        print(f"FAILED: {len(run.blocking_findings)} blocking finding(s)", file=sys.stderr)
        return 2
    if args.fail_on_review and review is not None and not review.approved:
        print(f"FAILED: preceptorship verdict is '{review.verdict}'", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
