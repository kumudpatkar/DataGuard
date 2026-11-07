
"""Run a DataGuard pipeline without opening the app.

Examples:
    python scripts/run_daily.py
    python scripts/run_daily.py --pipeline orders_vs_payments --threshold 85
    python scripts/run_daily.py --no-alert
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core.alerts import alert_if_needed
from core.pipeline import load_pipeline_files, run_pipeline
from core.reconciliation import ReconConfig
from core.utils import plain_money
from core.workflow import Workflow


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a DataGuard pipeline."
    )
    parser.add_argument(
        "--pipeline",
        default=None,
        help="Pipeline name from config/pipeline.yaml",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=config.DEFAULT_HEALTH_ALERT_THRESHOLD,
        help="Alert when the health score is below this value",
    )
    parser.add_argument(
        "--no-alert",
        action="store_true",
        help="Do not send alerts",
    )
    parser.add_argument(
        "--user",
        default="scheduler",
        help="Name recorded in the audit log",
    )

    args = parser.parse_args()

    # 1. Load pipeline configuration and input files.
    cfg = ReconConfig.from_yaml(config.PIPELINE_CONFIG, args.pipeline)
    source, target = load_pipeline_files(cfg)

    # 2. Execute reconciliation, risk, quality and health checks.
    out = run_pipeline(cfg, source, target)

    stats = out.recon.stats
    exceptions = out.exceptions

    # 3. Export exceptions report.
    report = (
        config.REPORTS_DIR
        / f"{cfg.name}_{date.today().isoformat()}.csv"
    )
    exceptions.sort_values(
        "Risk Score",
        ascending=False,
    ).to_csv(report, index=False)

    # 4. Save run and update ticket workflow.
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

    # 5. Print run summary.
    print(f"Pipeline        : {cfg.name}")
    print(
        f"Records         : {stats['total_records']:,}   "
        f"Exceptions: {stats['exceptions']:,}"
    )
    print(f"Match rate      : {stats['match_rate']:.1f}%")
    print(f"Money at risk   : {plain_money(out.risk['total_risk'])}")
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

    for _, finding in out.findings.head(3).iterrows():
        print(
            f"  Finding: {finding['Finding']} - "
            f"{finding['What we found']}"
        )

    # 6. Check alert threshold.
    below = out.health["score"] < args.threshold

    if below:
        print(
            f"Alert condition : Health score is below "
            f"{args.threshold}"
        )
    else:
        print(
            f"Alert condition : Health score meets the "
            f"threshold of {args.threshold}"
        )

    # 7. Send alert only when configured and enabled.
    if args.no_alert:
        print("Alert           : SKIPPED (--no-alert)")
    elif below:
        alert_result = alert_if_needed(
            cfg.name,
            out.health["score"],
            out.health["label"],
            args.threshold,
            stats["exceptions"],
            plain_money(out.risk["total_risk"]),
        )
        print(f"Alert           : {alert_result}")
    else:
        print("Alert           : Not required")

    return 1 if below else 0


if __name__ == "__main__":
    sys.exit(main())
