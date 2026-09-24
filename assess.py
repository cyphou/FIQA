#!/usr/bin/env python3
"""Fabric IQ Readiness Assessor — command line entry point.

Examples:
    python assess.py --inventory examples/sample_tenant --out artifacts
    python assess.py --inventory examples/sample_tenant --review --fail-on-blocking
    python assess.py --inventory examples/sample_tenant --lakehouse ./lakehouse
    python assess.py --inventory examples/sample_tenant --powerbi ./powerbi_report
    python assess.py --inventory examples/sample_tenant --calibration artifacts/calibration
    python assess.py --calibration-analyse artifacts/calibration/run_id_calibration_key.json --calibration-labels a=labels-a.csv b=labels-b.csv
    FABRIC_ACCESS_TOKEN=... python assess.py --live --tenant-id tenant-id --bearer-token-env FABRIC_ACCESS_TOKEN
    python assess.py --list-rules
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from fabric_iq import RULESET_VERSION, __version__
from fabric_iq.calibration import (
    CALIBRATION_SINK_ROOT,
    DEFAULT_SAMPLE_SIZE,
    DEFAULT_SEED,
    analyse,
    build_worksheet,
    read_labels,
    summarise,
    write_report,
    write_worksheet,
)
from fabric_iq.collectors import FabricApiCollector, FabricApiConfig, FabricHttpTransport, OfflineCollector
from fabric_iq.errors import AssessmentError
from fabric_iq.lakehouse import LakehouseWriter, select_comparable_history_runs, select_latest_baseline_run
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
    parser.add_argument(
        "--checkpoint",
        help=(
            "Path for resumable live-collection checkpoint data. "
            "PRIVACY: the checkpoint stores the tenant ID and the raw Bronze API payloads "
            "(including identity/role-assignment responses). Keep it inside the git-ignored "
            "artifacts/ folder, e.g. artifacts/live-checkpoint.json, and never commit it"
        ),
    )
    parser.add_argument(
        "--no-artifact-users",
        action="store_true",
        help=(
            "Do not request workspace role assignments during a live scan. "
            "Avoids reading named identities, at the cost of leaving the workspace "
            "permission rules unevaluated"
        ),
    )
    parser.add_argument(
        "--out",
        default="artifacts",
        help=(
            "Output folder for reports (default: artifacts, which is git-ignored). "
            "Reports carry run IDs, object names and findings — point this elsewhere only "
            "at a location that is also git-ignored"
        ),
    )
    parser.add_argument("--run-id", help="Run identifier (default: UTC timestamp)")
    parser.add_argument(
        "--lakehouse",
        help=(
            "Root folder for the Bronze/Silver/Gold medallion output. "
            "PRIVACY: Bronze holds raw collected payloads — keep this on a git-ignored path "
            "such as the documented ./lakehouse root"
        ),
    )
    parser.add_argument(
        "--powerbi",
        help=(
            "Root folder for a generated Power BI (.pbip) report project. "
            "PRIVACY: the generated data/Mart*.csv files are tenant-derived evidence "
            "(run IDs, object and workspace names, scores, findings) and the model.bim "
            "embeds absolute local paths — this output is never source and must never be "
            "committed. ./powerbi_report and Mart*.csv are git-ignored"
        ),
    )
    parser.add_argument(
        "--calibration",
        nargs="?",
        const=CALIBRATION_SINK_ROOT,
        help=(
            "Opt-in. Write a blinded practitioner-calibration worksheet for this run "
            f"(default folder: {CALIBRATION_SINK_ROOT}). Emits the blinded CSV, an "
            "instruction sheet, and a separate un-blinded key. "
            "PRIVACY: all three files are tenant-derived evidence — the worksheet carries "
            "measured object metadata and the key carries object names plus the tool's "
            "verdicts. Keep them on a git-ignored path and never commit them. Hand the "
            "worksheet to a labeler; never the key"
        ),
    )
    parser.add_argument(
        "--calibration-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Objects to sample for calibration (default: {DEFAULT_SAMPLE_SIZE}; roadmap band 20-30)",
    )
    parser.add_argument(
        "--calibration-seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Seed for the reproducible calibration draw (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--calibration-analyse",
        metavar="KEY_JSON",
        help=(
            "Analyse returned calibration worksheets against this key file and exit. "
            "Requires --calibration-labels. Reports inter-rater agreement first, then "
            "agreement with the tool, and enumerates every disagreement"
        ),
    )
    parser.add_argument(
        "--calibration-labels",
        nargs="+",
        metavar="[ID=]CSV",
        default=[],
        help=(
            "Filled worksheets returned by the labelers, as 'name=path.csv' or 'path.csv' "
            "(the file stem becomes the labeler id). Used with --calibration-analyse"
        ),
    )
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


def calibration_analysis(args) -> int:
    """Analyse returned worksheets against a key and write the agreement report.

    Output lands beside the key unless --calibration names a folder, so the analysis
    stays inside the same git-ignored evidence sink as the worksheet it came from.
    """
    if not args.calibration_labels:
        print(
            "error: --calibration-analyse requires --calibration-labels with at least "
            "one returned worksheet",
            file=sys.stderr,
        )
        return 1
    label_sets = []
    for entry in args.calibration_labels:
        labeler_id, separator, path = entry.partition("=")
        if not separator:
            labeler_id, path = None, entry
        label_sets.append(read_labels(path, labeler_id))
    report = analyse(args.calibration_analyse, label_sets)
    destination = args.calibration or os.path.dirname(os.path.abspath(args.calibration_analyse))
    written = write_report(report, destination)
    if not args.quiet:
        print(summarise(report))
    print(f"Calibration analysis written to {os.path.abspath(written['agreement'])}")
    if len(label_sets) < 2:
        print(
            "note: only one worksheet was supplied, so inter-rater agreement is "
            "undefined — agreement with the tool alone says nothing about the tool",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.version:
        print(f"fabric-iq-readiness {__version__} (ruleset {RULESET_VERSION})")
        return 0
    if args.list_rules:
        return list_rules()
    if args.calibration_analyse:
        try:
            return calibration_analysis(args)
        except AssessmentError as exc:
            print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    if args.calibration_labels:
        print(
            "error: --calibration-labels is only meaningful with --calibration-analyse",
            file=sys.stderr,
        )
        return 1
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
        history_runs = select_comparable_history_runs(args.out, run)
        baseline_run = history_runs[-1] if history_runs else select_latest_baseline_run(args.out, run)
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
                baseline_run=baseline_run,
                history_runs=history_runs,
            )

        if args.powerbi:
            PowerBiReportWriter(root=args.powerbi).write_run(
                run, backlog, baseline_run=baseline_run, history_runs=history_runs
            )

        if args.calibration:
            worksheet = build_worksheet(
                run, size=args.calibration_size, seed=args.calibration_seed
            )
            written = write_worksheet(worksheet, args.calibration)
            if not args.quiet:
                print(
                    f"Calibration worksheet: {len(worksheet.rows)} blinded object(s) at "
                    f"{os.path.abspath(written['worksheet'])}"
                )
                print(
                    "  hand the worksheet and the instructions to each labeler "
                    "independently; keep the key"
                )
                for note in worksheet.notes:
                    print(f"  ! {note}")

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
