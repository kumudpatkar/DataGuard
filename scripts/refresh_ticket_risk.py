
import sys
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from core.config import DB_PATH
from views.common import pipeline_config
from core.pipeline import load_pipeline_files, run_pipeline

PIPELINE = "orders_vs_payments"

EXPECTED_IDS = {
    13, 37, 42, 45, 47, 50, 59, 67,
    71, 90, 111, 121, 124, 146, 148
}

APPLY = "--apply" in sys.argv


def stop(message):
    raise RuntimeError(message)


def integrity_check(path):
    with sqlite3.connect(str(path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        stop(f"SQLite integrity check failed: {path}")
    return result


def get_current_values():
    cfg = pipeline_config(PIPELINE)
    source, target = load_pipeline_files(cfg)
    out = run_pipeline(cfg, source, target)

    df = out.results[
        out.results["Status"].astype(str).str.contains(
            "Duplicate", case=False, na=False
        )
    ][["Record Key", "Status", "Exposure", "Risk Score", "Priority"]].copy()

    df["Record Key"] = df["Record Key"].astype(str)
    df["Exposure"] = pd.to_numeric(df["Exposure"], errors="raise")
    df["Risk Score"] = pd.to_numeric(df["Risk Score"], errors="raise")
    df["Priority"] = df["Priority"].astype(str).str.strip()

    if len(df) != 15:
        stop(f"Expected 15 current duplicate rows; found {len(df)}.")

    if df.duplicated(["Record Key", "Status"]).any():
        stop("Duplicate current matching keys detected.")

    return df


def main():
    db_path = Path(DB_PATH).resolve()
    backup_path = db_path.parent / "dataguard_before_risk_fix.db"

    if not db_path.is_file():
        stop(f"Database not found: {db_path}")

    if not backup_path.is_file() or backup_path.stat().st_size == 0:
        stop("Backup missing or empty.")

    integrity_check(db_path)
    integrity_check(backup_path)

    print("Database integrity: OK")
    print("Backup integrity: OK")
    print("Mode:", "APPLY" if APPLY else "DRY RUN")

    current = get_current_values()

    with sqlite3.connect(str(db_path)) as conn:
        triggers = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type = 'trigger'
              AND lower(tbl_name) = 'exceptions'
        """).fetchall()

        if triggers:
            stop("Exceptions-table triggers found. Manual review required.")

        saved = pd.read_sql_query("""
            SELECT id, pipeline, record_key, issue_type,
                   exposure, risk_score, priority, status
            FROM exceptions
            WHERE pipeline = ?
              AND status IN ('Open', 'Investigating')
              AND issue_type LIKE 'Duplicate%'
        """, conn, params=(PIPELINE,))

    saved["record_key"] = saved["record_key"].astype(str)

    preview = current.merge(
        saved,
        left_on=["Record Key", "Status"],
        right_on=["record_key", "issue_type"],
        how="outer",
        indicator=True,
        validate="one_to_one"
    )

    if len(saved) != 15 or not (preview["_merge"] == "both").all():
        stop("Current and saved duplicate tickets do not match exactly.")

    if set(preview["id"].astype(int)) != EXPECTED_IDS:
        stop("Ticket IDs differ from the reviewed preview.")

    for _, row in preview.iterrows():
        if abs(float(row["exposure"]) - 2 * float(row["Exposure"])) > 0.03:
            stop(f"Unexpected exposure for ticket {row['id']}.")
        if abs(float(row["risk_score"]) - 2 * float(row["Risk Score"])) > 0.03:
            stop(f"Unexpected risk score for ticket {row['id']}.")

    print("\n--- VERIFIED TICKETS ---")
    print(preview[[
        "id", "Record Key", "Status",
        "exposure", "Exposure",
        "risk_score", "Risk Score",
        "priority", "Priority"
    ]].sort_values("id").to_string(index=False))

    if not APPLY:
        print("\nDRY RUN ONLY. Database was not modified.")
        print("After reviewing, run this script with --apply.")
        return

    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.isolation_level = None

    try:
        conn.execute("BEGIN IMMEDIATE")

        for _, row in preview.iterrows():
            fresh = conn.execute("""
                SELECT record_key, issue_type, exposure,
                       risk_score, priority, status
                FROM exceptions
                WHERE id = ? AND pipeline = ?
            """, (int(row["id"]), PIPELINE)).fetchone()

            if fresh is None:
                stop(f"Ticket {row['id']} disappeared.")

            if (
                str(fresh[0]) != str(row["Record Key"])
                or str(fresh[1]) != str(row["Status"])
                or str(fresh[5]) not in ("Open", "Investigating")
                or abs(float(fresh[2]) - float(row["exposure"])) > 0.001
                or abs(float(fresh[3]) - float(row["risk_score"])) > 0.001
                or str(fresh[4]) != str(row["priority"])
            ):
                stop(f"Ticket {row['id']} changed. Aborting.")

        for _, row in preview.iterrows():
            cur = conn.execute("""
                UPDATE exceptions
                SET exposure = ?, risk_score = ?, priority = ?
                WHERE id = ?
                  AND pipeline = ?
                  AND record_key = ?
                  AND issue_type = ?
                  AND status IN ('Open', 'Investigating')
            """, (
                float(row["Exposure"]),
                float(row["Risk Score"]),
                str(row["Priority"]),
                int(row["id"]),
                PIPELINE,
                str(row["Record Key"]),
                str(row["Status"])
            ))

            if cur.rowcount != 1:
                stop(f"Ticket {row['id']} did not update exactly once.")

        for _, row in preview.iterrows():
            check = conn.execute("""
                SELECT exposure, risk_score, priority, status
                FROM exceptions WHERE id = ? AND pipeline = ?
            """, (int(row["id"]), PIPELINE)).fetchone()

            if (
                check is None
                or abs(float(check[0]) - float(row["Exposure"])) > 0.001
                or abs(float(check[1]) - float(row["Risk Score"])) > 0.001
                or str(check[2]) != str(row["Priority"])
                or str(check[3]) != str(row["status"])
            ):
                stop(f"Post-update verification failed for {row['id']}.")

        conn.execute("COMMIT")
        print("\nSUCCESS: 15 duplicate tickets updated and verified.")

    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    integrity_check(db_path)
    print("Post-update database integrity: OK")


if __name__ == "__main__":
    main()
