"""Exception workflow: turn every exception into a ticket someone owns.

Finding a mismatch is only half of the job. A real finance team must also
assign it, discuss it, and close it. This module stores that in a small
SQLite database (one file, no server needed) with four tables:

    runs        every reconciliation run with its health score
    exceptions  one ticket per (pipeline, record key, issue type)
    comments    discussion on a ticket
    audit_log   who changed what and when

When a new run no longer contains an exception that was Open or Investigating,
the ticket is closed automatically as "Resolved (auto)".
When a Fixed ticket shows up again, it is re-opened.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.config import DB_PATH

STATUSES = ["Open", "Investigating", "Fixed", "Ignored", "Resolved (auto)"]
ACTIVE_STATUSES = ("Open", "Investigating")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline TEXT NOT NULL,
    run_at TEXT NOT NULL,
    run_by TEXT,
    source_rows INTEGER, target_rows INTEGER, total_records INTEGER,
    matched INTEGER, exceptions INTEGER,
    match_rate REAL, total_risk REAL, health_score REAL, rule_pass_rate REAL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline TEXT NOT NULL,
    record_key TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    details TEXT,
    exposure REAL, risk_score REAL, priority TEXT,
    status TEXT NOT NULL DEFAULT 'Open',
    assigned_to TEXT DEFAULT '',
    first_seen_run INTEGER, last_seen_run INTEGER,
    created_at TEXT, updated_at TEXT,
    UNIQUE (pipeline, record_key, issue_type)
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exception_id INTEGER NOT NULL,
    author TEXT, body TEXT, created_at TEXT,
    FOREIGN KEY (exception_id) REFERENCES exceptions(id)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT, user TEXT, action TEXT, entity TEXT, entity_id TEXT, details TEXT
);
CREATE INDEX IF NOT EXISTS idx_exceptions_status ON exceptions (pipeline, status);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Workflow:
    """Small data-access layer for runs, tickets, comments and the audit log."""

    

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.executescript(SCHEMA)

            # Safely add resolution_note to the existing database.
            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(exceptions)"
                ).fetchall()
            }

            if "resolution_note" not in columns:
                conn.execute(
                    "ALTER TABLE exceptions ADD COLUMN resolution_note TEXT"
                )



    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ audit
    def _audit(self, conn, user, action, entity, entity_id, details=""):
        conn.execute(
            "INSERT INTO audit_log (at, user, action, entity, entity_id, details) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), user or "system", action, entity, str(entity_id), details),
        )

    def audit_log(self, limit: int = 200) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT at AS 'When', user AS 'User', action AS 'Action', entity AS 'Entity', "
                "entity_id AS 'Id', details AS 'Details' FROM audit_log ORDER BY id DESC LIMIT ?",
                conn, params=(limit,),
            )

    # ------------------------------------------------------------------- runs
    def save_run(self, pipeline: str, with_risk: pd.DataFrame, stats: dict,
                 health_score: float, rule_pass_rate: float, total_risk: float,
                 user: str = "system", note: str = "") -> dict:
        """Store a run and create, update, re-open or auto-close tickets."""
        exceptions = with_risk[with_risk["Status"] != "Matched"]
        now = _now()

        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (pipeline, run_at, run_by, source_rows, target_rows, total_records, "
                "matched, exceptions, match_rate, total_risk, health_score, rule_pass_rate, note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pipeline, now, user, stats["source_rows"], stats["target_rows"],
                 stats["total_records"], stats["matched"], stats["exceptions"],
                 stats["match_rate"], total_risk, health_score, rule_pass_rate, note),
            )
            run_id = cur.lastrowid

            existing = {
                (r["record_key"], r["issue_type"]): (r["id"], r["status"])
                for r in conn.execute(
                    "SELECT id, record_key, issue_type, status FROM exceptions WHERE pipeline = ?",
                    (pipeline,),
                )
            }

            new_rows, update_rows, reopen_ids, seen = [], [], [], set()
            columns = ["Record Key", "Status", "Details", "Exposure", "Risk Score", "Priority"]
            for record_key, issue, details, exposure, risk, priority in exceptions[columns].itertuples(
                    index=False, name=None):
                key = (str(record_key), str(issue))
                seen.add(key)
                values = (str(details), float(exposure), float(risk), str(priority))
                if key in existing:
                    ticket_id, status = existing[key]
                    update_rows.append((*values, run_id, now, ticket_id))
                    if status in ("Fixed", "Resolved (auto)"):
                        reopen_ids.append(ticket_id)
                else:
                    new_rows.append((pipeline, key[0], key[1], *values, "Open", "",
                                     run_id, run_id, now, now))

            conn.executemany(
                "INSERT INTO exceptions (pipeline, record_key, issue_type, details, exposure, "
                "risk_score, priority, status, assigned_to, first_seen_run, last_seen_run, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", new_rows)
            conn.executemany(
                "UPDATE exceptions SET details=?, exposure=?, risk_score=?, priority=?, "
                "last_seen_run=?, updated_at=? WHERE id=?", update_rows)
            for ticket_id in reopen_ids:
                conn.execute("UPDATE exceptions SET status='Open' WHERE id=?", (ticket_id,))
                self._audit(conn, "system", "Re-opened", "exception", ticket_id,
                            f"Appeared again in run {run_id}")

            auto_closed = 0
            for key, (ticket_id, status) in existing.items():
                if key not in seen and status in ACTIVE_STATUSES:
                    conn.execute(
                        "UPDATE exceptions SET status='Resolved (auto)', updated_at=? WHERE id=?",
                        (now, ticket_id))
                    auto_closed += 1
            if auto_closed:
                self._audit(conn, "system", "Auto-resolved", "run", run_id,
                            f"{auto_closed} tickets no longer appear in the data")

            self._audit(conn, user, "Saved run", "run", run_id,
                        f"{pipeline}: {len(new_rows)} new, {len(update_rows)} still present, "
                        f"{auto_closed} auto-resolved")

        return {"run_id": run_id, "new": len(new_rows), "still_present": len(update_rows),
                "reopened": len(reopen_ids), "auto_resolved": auto_closed}

    def list_runs(self, pipeline: str | None = None) -> pd.DataFrame:
        query = ("SELECT id AS 'Run', pipeline AS 'Pipeline', run_at AS 'Run At', run_by AS 'Run By', "
                 "total_records AS 'Records', matched AS 'Matched', exceptions AS 'Exceptions', "
                 "ROUND(match_rate, 2) AS 'Match Rate %', ROUND(total_risk, 2) AS 'Money at Risk', "
                 "ROUND(health_score, 1) AS 'Health Score', ROUND(rule_pass_rate, 1) AS 'Rule Pass %' "
                 "FROM runs")
        params: tuple = ()
        if pipeline:
            query += " WHERE pipeline = ?"
            params = (pipeline,)
        query += " ORDER BY id"
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    # -------------------------------------------------------------- tickets
    def list_exceptions(self, pipeline: str | None = None, statuses=None,
                        priorities=None, assigned_to: str | None = None) -> pd.DataFrame:
        query = ("SELECT id AS 'Ticket', pipeline AS 'Pipeline', record_key AS 'Record Key', "
                 "issue_type AS 'Issue', priority AS 'Priority', ROUND(risk_score, 2) AS 'Risk Score', "
                 "ROUND(exposure, 2) AS 'Exposure', status AS 'Status', assigned_to AS 'Assigned To', "
                
                 "details AS 'Details', resolution_note AS 'Resolution Note', "
                 "first_seen_run AS 'First Run', last_seen_run AS 'Last Run', "
                 "updated_at AS 'Updated' FROM exceptions WHERE 1=1")

        params: list = []
        if pipeline:
            query += " AND pipeline = ?"
            params.append(pipeline)
        if statuses:
            query += f" AND status IN ({','.join('?' * len(statuses))})"
            params += list(statuses)
        if priorities:
            query += f" AND priority IN ({','.join('?' * len(priorities))})"
            params += list(priorities)
        if assigned_to:
            query += " AND assigned_to = ?"
            params.append(assigned_to)
        query += " ORDER BY risk_score DESC"
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def update_exceptions(self, ids: list[int], user: str, status: str | None = None,
                          assigned_to: str | None = None) -> int:
        """Change status and/or owner of one or more tickets."""
        if not ids:
            return 0
        if status is not None and status not in STATUSES:
            raise ValueError(f"Unknown status '{status}'")
        changed = 0
        with self._connect() as conn:
            for ticket_id in ids:
                row = conn.execute("SELECT status, assigned_to FROM exceptions WHERE id=?",
                                   (int(ticket_id),)).fetchone()
                if row is None:
                    continue
                new_status = status if status is not None else row["status"]
                new_owner = assigned_to if assigned_to is not None else row["assigned_to"]
                if new_status == row["status"] and new_owner == row["assigned_to"]:
                    continue
                conn.execute("UPDATE exceptions SET status=?, assigned_to=?, updated_at=? WHERE id=?",
                             (new_status, new_owner, _now(), int(ticket_id)))
                self._audit(conn, user, "Updated ticket", "exception", ticket_id,
                            f"status: {row['status']} -> {new_status}; "
                            f"owner: '{row['assigned_to']}' -> '{new_owner}'")
                changed += 1
        return changed

    def add_comment(self, exception_id: int, author: str, body: str) -> None:
        body = (body or "").strip()
        if not body:
            return
        with self._connect() as conn:
            conn.execute("INSERT INTO comments (exception_id, author, body, created_at) "
                         "VALUES (?,?,?,?)", (int(exception_id), author or "unknown", body, _now()))
            self._audit(conn, author, "Commented", "exception", exception_id, body[:200])

    
    def save_resolution_note(
        self,
        exception_id: int,
        user: str,
        note: str,
    ) -> bool:
        """Save a resolution note and record the change in the audit log."""
        note = (note or "").strip()

        if not note:
            return False

        with self._connect() as conn:
            row = conn.execute(
                "SELECT status, resolution_note FROM exceptions WHERE id = ?",
                (int(exception_id),),
            ).fetchone()

            if row is None:
                return False

            conn.execute(
                "UPDATE exceptions SET resolution_note = ?, updated_at = ? WHERE id = ?",
                (note, _now(), int(exception_id)),
            )

            self._audit(
                conn,
                user,
                "Resolution note updated",
                "exception",
                exception_id,
                f"Status: {row['status']}; Note: {note[:200]}",
            )

        return True


    def list_comments(self, exception_id: int) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT created_at AS 'When', author AS 'Who', body AS 'Comment' "
                "FROM comments WHERE exception_id = ? ORDER BY id",
                conn, params=(int(exception_id),))

    def status_counts(self, pipeline: str | None = None) -> dict:
        query = "SELECT status, COUNT(*) AS n FROM exceptions"
        params: tuple = ()
        if pipeline:
            query += " WHERE pipeline = ?"
            params = (pipeline,)
        query += " GROUP BY status"
        with self._connect() as conn:
            return {r["status"]: r["n"] for r in conn.execute(query, params)}

    def open_risk(self, pipeline: str | None = None) -> float:
        """Money still at risk in tickets that are not closed."""
        query = "SELECT COALESCE(SUM(risk_score), 0) AS r FROM exceptions WHERE status IN ('Open','Investigating')"
        params: tuple = ()
        if pipeline:
            query += " AND pipeline = ?"
            params = (pipeline,)
        with self._connect() as conn:
            return float(conn.execute(query, params).fetchone()["r"])

    def reset(self, user: str = "system") -> None:
        """Delete all runs, tickets and comments (the audit log keeps one entry)."""
        with self._connect() as conn:
            for table in ("comments", "exceptions", "runs"):
                conn.execute(f"DELETE FROM {table}")
            self._audit(conn, user, "Reset database", "all", "-", "All runs and tickets deleted")
