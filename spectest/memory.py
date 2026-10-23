"""SQLite persistent memory: spec baselines, generated suites, and test runs."""
import sqlite3
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS spec_baselines (
    spec_id TEXT PRIMARY KEY,
    spec_hash TEXT NOT NULL,
    spec_content TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS generated_test_suites (
    suite_id TEXT PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    spec_hash TEXT NOT NULL,
    test_code TEXT NOT NULL,
    status TEXT CHECK(status IN ('CURRENT', 'SUPERSEDED')) DEFAULT 'CURRENT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
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
-- 4. What the agent learned: tests it had to repair, fed back into future test generation
CREATE TABLE IF NOT EXISTS lessons (
    lesson_id TEXT PRIMARY KEY,
    spec_hash TEXT NOT NULL,
    test_name TEXT NOT NULL,
    lesson TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Columns added after the first release; ALTERed into older databases on open.
MIGRATIONS = {"test_runs": {"failure_analysis": "TEXT", "repairs": "TEXT"}}


class Memory:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        for table, columns in MIGRATIONS.items():
            existing = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
            for column, kind in columns.items():
                if column not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        self.conn.commit()

    def close(self):
        self.conn.close()

    # --- spec baselines -------------------------------------------------
    def latest_baseline(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM spec_baselines ORDER BY version DESC LIMIT 1"
        ).fetchone()

    def add_baseline(self, project_id: str, spec_hash: str, content: str) -> int:
        latest = self.latest_baseline()
        version = (latest["version"] + 1) if latest else 1
        with self.conn:
            self.conn.execute(
                "INSERT INTO spec_baselines (spec_id, spec_hash, spec_content, version) VALUES (?, ?, ?, ?)",
                (f"{project_id}:v{version}", spec_hash, content, version),
            )
        return version

    # --- test suites ----------------------------------------------------
    def current_suite(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM generated_test_suites WHERE status = 'CURRENT' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

    def save_suite(self, commit_sha: str, spec_hash: str, test_code: str) -> str:
        suite_id = str(uuid.uuid4())
        with self.conn:  # supersede + insert atomically
            self.conn.execute("UPDATE generated_test_suites SET status = 'SUPERSEDED' WHERE status = 'CURRENT'")
            self.conn.execute(
                "INSERT INTO generated_test_suites (suite_id, commit_sha, spec_hash, test_code) VALUES (?, ?, ?, ?)",
                (suite_id, commit_sha, spec_hash, test_code),
            )
        return suite_id

    # --- test runs ------------------------------------------------------
    def last_run(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM test_runs ORDER BY run_timestamp DESC, rowid DESC LIMIT 1"
        ).fetchone()

    def save_run(self, suite_id, commit_sha, total, passed, failed, stderr_log, analysis, repairs="") -> str:
        run_id = str(uuid.uuid4())
        with self.conn:
            self.conn.execute(
                """INSERT INTO test_runs (run_id, suite_id, commit_sha, total_tests, passed_tests,
                   failed_tests, stderr_log, failure_analysis, repairs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, suite_id, commit_sha, total, passed, failed, stderr_log, analysis, repairs),
            )
        return run_id

    def recent_runs(self, limit: int = 3) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM test_runs ORDER BY run_timestamp DESC, rowid DESC LIMIT ?", (limit,)
        ).fetchall()

    # --- lessons ----------------------------------------------------------
    def add_lesson(self, spec_hash: str, test_name: str, lesson: str):
        with self.conn:
            self.conn.execute("INSERT INTO lessons (lesson_id, spec_hash, test_name, lesson) VALUES (?, ?, ?, ?)",
                              (str(uuid.uuid4()), spec_hash, test_name, lesson))

    def recent_lessons(self, limit: int = 10) -> list[str]:
        rows = self.conn.execute(
            "SELECT test_name, lesson FROM lessons ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        return [f"{r['test_name']}: {r['lesson']}" for r in rows]

    def email_already_sent(self, commit_sha: str, suite_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM test_runs WHERE commit_sha = ? AND suite_id = ? AND email_sent = 1",
            (commit_sha, suite_id),
        ).fetchone()
        return row is not None

    def mark_email_sent(self, run_id: str):
        with self.conn:
            self.conn.execute("UPDATE test_runs SET email_sent = 1 WHERE run_id = ?", (run_id,))

    def history(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM test_runs ORDER BY run_timestamp, rowid"
        ).fetchall()
