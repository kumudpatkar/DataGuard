
"""Run a DataGuard reconciliation pipeline and save its daily report."""

from __future__ import annotations

import argparse
from datetime import date

from core import config
from core.alerts import alert_if_needed
from core.pipeline import load_pipeline_files, run_pipeline
from core.reconciliation import ReconConfig
from core.workflow import Workflow
from core.utils import plain_money


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the DataGuard daily reconciliation pipeline."
    )

    parser.add_argument(
        "--pipeline",
        default=None,
        help="Pipeline name from config/pipeline.yaml.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=config.DEFAULT_HEALTH_ALERT_THRESHOLD,
        help="Health score threshold for alerts.",
    )
    parser.add_argument(
        "--no-alert",
        action="store_true",
        help="Skip sending alerts.",
    )
    parser.add_argument(
        "--user",
        default="system",
        help="User name recorded in the workflow audit.",
    )

    return parser.parse_args()


def main():
    """Execute one reconciliation run."""
    args = parse_args()

    # 1. Load pipeline configuration.
    cfg = ReconConfig.from_yaml(
        config.PIPELINE_CONFIG,
        args.pipeline,
    )

    # 2. Load source and target files.
    source, target = load_pipeline_files(cfg)

    # 3. Run reconciliation and analytics.
    out = run_pipeline(cfg, source, target)
    stats = out.recon.stats

    # 4. Export exception report.
    config.REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = (
        config.REPORTS_DIR
        / f"{cfg.name}_{date.today().isoformat()}.csv"
    )

    out.exceptions.to_csv(
        report,
        index=False,
    )

    # 5. Save run and workflow.
    workflow = Workflow()

    saved = workflow.save_run(
        pipeline=cfg.name,
        with_risk=out.results,
        stats=stats,
        health_score=out.health["score"],
        rule_pass_rate=out.rule_pass_rate,
        total_risk=out.risk["total_risk"],
        user=args.user,
    )

    # 6. Print run summary.
    print(f"Pipeline        : {cfg.name}")
    print(
        f"Records         : {stats['total_records']:,}   "
        f"Exceptions: {stats['exceptions']:,}"
    )
    print(
        f"Match rate      : "
        f"{stats['match_rate']:.1f}%"
    )
    print(
        f"Row Match Rate  : "
        f"{stats.get('row_match_rate', stats['match_rate']):.1f}%"
    )
    print(
        f"Money at risk   : "
        f"{plain_money(out.risk['total_risk'])}"
    )
    print(
        f"Health score    : "
        f"{out.health['score']} ({out.health['label']})"
    )
    print(f"Run ID          : {saved['run_id']}")
    print(
        f"Tickets         : New {saved['new']}, "
        f"Existing {saved['still_present']}, "
        f"Reopened {saved['reopened']}, "
        f"Auto-resolved {saved['auto_resolved']}"
    )
    print(f"Exceptions saved: {report}")

    # 7. Print top findings.
    for _, finding in out.findings.head(3).iterrows():
        print(
            f"  Finding: {finding['Finding']} - "
            f"{finding['What we found']}"
        )

    # 8. Check health threshold and send alerts if enabled.
    below = out.health["score"] < args.threshold

    if args.no_alert:
        print("Alerts          : Skipped (--no-alert)")
    elif below:
        alert_if_needed(
            out.health["score"],
            args.threshold,
            cfg.name,
            out.risk["total_risk"],
        )
    else:
        print("Alerts          : Not required")

    return 1 if below else 0


if __name__ == "__main__":
    raise SystemExit(main())
