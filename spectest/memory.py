"""SQLite persistent memory, one database per project (`.spectest/spectest.db`).

Tables: what the spec said (spec_baselines), the tests generated from it (generated_test_suites), what happened
on each run (test_runs), what the agent learned (lessons), repairs waiting for the developer (approvals),
and every report delivery attempt (notifications). Old records are superseded, never overwritten.
"""
import sqlite3
import uuid
from pathlib import Path
from typing import Callable

SCHEMA = """
-- 0. Which project this database belongs to (one database per project keeps projects isolated)
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- 1. Every version of the spec (the approved baseline the tests are generated from)
CREATE TABLE IF NOT EXISTS spec_baselines (
    spec_id TEXT PRIMARY KEY,
    spec_hash TEXT NOT NULL,
    spec_content TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- 2. Every generated test suite; exactly one is CURRENT, older ones are kept as SUPERSEDED
CREATE TABLE IF NOT EXISTS generated_test_suites (
    suite_id TEXT PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    spec_hash TEXT NOT NULL,
    test_code TEXT NOT NULL,
    status TEXT CHECK(status IN ('CURRENT', 'SUPERSEDED')) DEFAULT 'CURRENT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- 3. Every run: counts from pytest, the agent's diagnosis, repairs, and whether the report was delivered
CREATE TABLE IF NOT EXISTS test_runs (
    run_id TEXT PRIMARY KEY,
    suite_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    total_tests INTEGER NOT NULL,
    passed_tests INTEGER NOT NULL,
    failed_tests INTEGER NOT NULL,
    stderr_log TEXT,
    failure_analysis TEXT,
    repairs TEXT,
    email_sent BOOLEAN DEFAULT 0,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(suite_id) REFERENCES generated_test_suites(suite_id)
);
-- 4. What the agent learned from repairs; only APPROVED lessons are fed into later test generation
CREATE TABLE IF NOT EXISTS lessons (
    lesson_id TEXT PRIMARY KEY,
    spec_hash TEXT NOT NULL,
    test_name TEXT NOT NULL,
    lesson TEXT NOT NULL,
    approval_id TEXT,
    status TEXT CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED')) DEFAULT 'APPROVED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- 5. Agent test repairs awaiting the developer's decision (agent suggestion kept separate from approval)
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    run_id TEXT,
    suite_id TEXT NOT NULL,
    previous_suite_id TEXT NOT NULL,
    details TEXT NOT NULL,
    status TEXT CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED')) DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP
);
-- 6. Every report delivery attempt: approval rule, outcome and error recorded separately
CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    suite_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    approval TEXT NOT NULL,
    outcome TEXT CHECK(outcome IN ('sent', 'saved_to_outbox', 'failed')) NOT NULL,
    error TEXT,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Columns added after the first release; ALTERed into older databases on open.
MIGRATIONS = {"test_runs": {"failure_analysis": "TEXT", "repairs": "TEXT"},
              "lessons": {"approval_id": "TEXT", "status": "TEXT DEFAULT 'APPROVED'"}}


class ProjectMismatch(ValueError):
    pass


def self_path_hint(owner: str, requested: str) -> str:
    return (f"this .spectest memory belongs to project {owner!r}, but SPECTEST.md says project_id: {requested}. "
            f"Projects never share memory; if you renamed the project, set project_id back to {owner!r}.")


class Memory:
    def __init__(self, db_path: Path, project_id: str | None = None,
                 on_event: Callable[[str, str, str], None] | None = None):
        """Open (or create) a project's memory. `on_event(kind, table, detail)` is called on every read/write
        so the agent log can show memory use; `kind` is "memory_read" or "memory_write"."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.on_event = on_event or (lambda kind, table, detail: None)
        self.conn.executescript(SCHEMA)
        for table, columns in MIGRATIONS.items():
            existing = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
            for column, kind in columns.items():
                if column not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        self.conn.commit()
        if project_id:
            self._claim(project_id)

    def _claim(self, project_id: str):
        """Bind this database to one project; refuse to open another project's memory."""
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'project_id'").fetchone()
        if row is None:
            with self.conn:
                self.conn.execute("INSERT INTO meta (key, value) VALUES ('project_id', ?)", (project_id,))
        elif row["value"] != project_id:
            self.conn.close()
            raise ProjectMismatch(f"{self_path_hint(row['value'], project_id)}")

    def close(self):
        self.conn.close()

    def _read(self, table: str, detail: str):
        self.on_event("memory_read", table, detail)

    def _write(self, table: str, detail: str):
        self.on_event("memory_write", table, detail)

    @property
    def project_id(self) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'project_id'").fetchone()
        return row["value"] if row else None

    # --- spec baselines -------------------------------------------------
    def latest_baseline(self) -> sqlite3.Row | None:
        row = self.conn.execute("SELECT * FROM spec_baselines ORDER BY version DESC LIMIT 1").fetchone()
        self._read("spec_baselines", f"latest version: {row['version'] if row else 'none'}")
        return row

    def add_baseline(self, project_id: str, spec_hash: str, content: str) -> int:
        latest = self.conn.execute("SELECT MAX(version) FROM spec_baselines").fetchone()[0]
        version = (latest or 0) + 1
        with self.conn:
            self.conn.execute(
                "INSERT INTO spec_baselines (spec_id, spec_hash, spec_content, version) VALUES (?, ?, ?, ?)",
                (f"{project_id}:v{version}", spec_hash, content, version),
            )
        self._write("spec_baselines", f"v{version} ({spec_hash[:12]})")
        return version

    # --- test suites ----------------------------------------------------
    def current_suite(self) -> sqlite3.Row | None:
        row = self.conn.execute(
            "SELECT * FROM generated_test_suites WHERE status = 'CURRENT' ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        self._read("generated_test_suites", f"current: {row['suite_id'][:8] if row else 'none'}")
        return row

    def suite(self, suite_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM generated_test_suites WHERE suite_id = ?", (suite_id,)).fetchone()

    def save_suite(self, commit_sha: str, spec_hash: str, test_code: str) -> str:
        suite_id = str(uuid.uuid4())
        with self.conn:  # supersede + insert atomically
            self.conn.execute("UPDATE generated_test_suites SET status = 'SUPERSEDED' WHERE status = 'CURRENT'")
            self.conn.execute(
                "INSERT INTO generated_test_suites (suite_id, commit_sha, spec_hash, test_code) VALUES (?, ?, ?, ?)",
                (suite_id, commit_sha, spec_hash, test_code),
            )
        self._write("generated_test_suites", f"new CURRENT {suite_id[:8]}; previous SUPERSEDED")
        return suite_id

    # --- test runs ------------------------------------------------------
    def last_run(self) -> sqlite3.Row | None:
        row = self.conn.execute("SELECT * FROM test_runs ORDER BY run_timestamp DESC, rowid DESC LIMIT 1").fetchone()
        self._read("test_runs", f"last run: {row['commit_sha'][:16] if row else 'none'}")
        return row

    def save_run(self, suite_id, commit_sha, total, passed, failed, stderr_log, analysis, repairs="") -> str:
        run_id = str(uuid.uuid4())
        with self.conn:
            self.conn.execute(
                """INSERT INTO test_runs (run_id, suite_id, commit_sha, total_tests, passed_tests,
                   failed_tests, stderr_log, failure_analysis, repairs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, suite_id, commit_sha, total, passed, failed, stderr_log, analysis, repairs),
            )
        self._write("test_runs", f"run {run_id[:8]}: {passed}/{total} passed")
        return run_id

    def recent_runs(self, limit: int = 3) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            "SELECT * FROM test_runs ORDER BY run_timestamp DESC, rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        self._read("test_runs", f"{len(rows)} recent runs")
        return rows

    def history(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM test_runs ORDER BY run_timestamp, rowid").fetchall()

    # --- lessons ----------------------------------------------------------
    def add_lesson(self, spec_hash: str, test_name: str, lesson: str, approval_id: str | None = None):
        status = "PENDING" if approval_id else "APPROVED"
        with self.conn:
            self.conn.execute(
                "INSERT INTO lessons (lesson_id, spec_hash, test_name, lesson, approval_id, status) "
                "VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), spec_hash, test_name, lesson, approval_id, status))
        self._write("lessons", f"{test_name} ({status})")

    def recent_lessons(self, limit: int = 10) -> list[str]:
        """Approved lessons only: a repair the developer rejected (or hasn't reviewed) must not teach anything."""
        rows = self.conn.execute(
            "SELECT test_name, lesson FROM lessons WHERE status = 'APPROVED' "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        self._read("lessons", f"{len(rows)} approved lessons")
        return [f"{r['test_name']}: {r['lesson']}" for r in rows]

    # --- approvals ----------------------------------------------------------
    def add_approval(self, kind: str, run_id: str | None, suite_id: str, previous_suite_id: str, details: str) -> str:
        approval_id = str(uuid.uuid4())
        with self.conn:
            self.conn.execute(
                "INSERT INTO approvals (approval_id, kind, run_id, suite_id, previous_suite_id, details) "
                "VALUES (?, ?, ?, ?, ?, ?)", (approval_id, kind, run_id, suite_id, previous_suite_id, details))
        self._write("approvals", f"{kind} {approval_id[:8]} PENDING")
        return approval_id

    def attach_approval_run(self, approval_id: str, run_id: str):
        with self.conn:
            self.conn.execute("UPDATE approvals SET run_id = ? WHERE approval_id = ?", (run_id, approval_id))

    def pending_approvals(self) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            "SELECT * FROM approvals WHERE status = 'PENDING' ORDER BY created_at, rowid").fetchall()
        self._read("approvals", f"{len(rows)} pending")
        return rows

    def decide_approval(self, approval_id: str, approved: bool):
        status = "APPROVED" if approved else "REJECTED"
        with self.conn:
            self.conn.execute("UPDATE approvals SET status = ?, decided_at = CURRENT_TIMESTAMP "
                              "WHERE approval_id = ? AND status = 'PENDING'", (status, approval_id))
            self.conn.execute("UPDATE lessons SET status = ? WHERE approval_id = ?", (status, approval_id))
        self._write("approvals", f"{approval_id[:8]} {status}")

    # --- notifications ------------------------------------------------------
    def email_already_sent(self, commit_sha: str, suite_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM test_runs WHERE commit_sha = ? AND suite_id = ? AND email_sent = 1", (commit_sha, suite_id),
        ).fetchone()
        self._read("test_runs", f"report already delivered for {commit_sha[:12]}: {row is not None}")
        return row is not None

    def mark_email_sent(self, run_id: str):
        with self.conn:
            self.conn.execute("UPDATE test_runs SET email_sent = 1 WHERE run_id = ?", (run_id,))
        self._write("test_runs", f"run {run_id[:8]} report delivered")

    def add_notification(self, run_id: str, commit_sha: str, suite_id: str, recipient: str, approval: str,
                         outcome: str, error: str = ""):
        with self.conn:
            self.conn.execute(
                "INSERT INTO notifications (notification_id, run_id, commit_sha, suite_id, recipient, approval, "
                "outcome, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), run_id, commit_sha, suite_id, recipient, approval, outcome, error))
        self._write("notifications", f"{outcome} -> {recipient or '(outbox)'}")

    def notifications(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM notifications ORDER BY attempted_at, rowid").fetchall()
