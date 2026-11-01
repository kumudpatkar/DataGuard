"""Run a DataGuard pipeline without opening the app (for daily automation).

Examples (run from the project folder):

    python scripts/run_daily.py
    python scripts/run_daily.py --pipeline orders_vs_payments --threshold 85
    python scripts/run_daily.py --no-alert

What it does:  reconcile -> score risk -> find root causes -> run rules ->
               compute health -> save the run and tickets -> export a CSV ->
               send an alert if the health score is below the threshold.

Exit code: 0 if the health score is at or above the threshold, 1 if it is below.
That makes it easy to use with Windows Task Scheduler, cron, or GitHub Actions.

Schedule it every morning at 08:00
----------------------------------
Linux / macOS (cron):
    0 8 * * *  cd /path/to/DataGuard && .venv/bin/python scripts/run_daily.py

Windows (Task Scheduler): create a task that runs
    <project>\\.venv\\Scripts\\python.exe  scripts\\run_daily.py
with "Start in" set to the project folder.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config                                   # noqa: E402
from core.alerts import alert_if_needed                    # noqa: E402
from core.pipeline import load_pipeline_files, run_pipeline  # noqa: E402
from core.reconciliation import ReconConfig                # noqa: E402
from core.utils import plain_money                         # noqa: E402



def main() -> int:
    parser = argparse.ArgumentParser(description="Run a DataGuard pipeline.")
    parser.add_argument("--pipeline", default=None, help="Pipeline name from config/pipeline.yaml")
    parser.add_argument("--threshold", type=float, default=config.DEFAULT_HEALTH_ALERT_THRESHOLD,
                        help="Alert when the health score is below this value")
    parser.add_argument("--no-alert", action="store_true", help="Do not send alerts")
    parser.add_argument("--user", default="scheduler", help="Name recorded in the audit log")
    args = parser.parse_args()

    cfg = ReconConfig.from_yaml(config.PIPELINE_CONFIG, args.pipeline)
    source, target = load_pipeline_files(cfg)
    out = run_pipeline(cfg, source, target)

    
    saved = None


    report = config.REPORTS_DIR / f"{cfg.name}_{date.today().isoformat()}.csv"
    out.exceptions.sort_values("Risk Score", ascending=False).to_csv(report, index=False)

    stats = out.recon.stats
    print(f"Pipeline        : {cfg.name}")
    print(f"Records         : {stats['total_records']:,}   Exceptions: {stats['exceptions']:,}")
    print(f"Match rate      : {stats['match_rate']:.1f}%")
    print(f"Money at risk   : {plain_money(out.risk['total_risk'])}")
    print(f"Health score    : {out.health['score']} ({out.health['label']})")
    print("Ticket workflow : SKIPPED (safe report-only test)")
    print(f"Exceptions saved: {report}")
    for _, finding in out.findings.head(3).iterrows():
        print(f"  Finding: {finding['Finding']} - {finding['What we found']}")

    
    below = out.health["score"] < args.threshold
    if below:
        print(f"Alert condition : Health score is below {args.threshold}")
    else:
        print(f"Alert condition : Health score meets the threshold of {args.threshold}")

    print("Alert           : SKIPPED (safe test mode)")
    return 1 if below else 0



if __name__ == "__main__":
    sys.exit(main())
