"""Print a project's SpecTest memory (SQLite tables) and its most recent action-log events.

    python scripts/inspect_memory.py [project_folder] [--events N]

Read-only: opens .spectest/spectest.db and .spectest/logs/agent.jsonl and prints them in a readable form.
"""
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

COLUMNS = {
    "meta": ["key", "value"],
    "spec_baselines": ["version", "spec_hash", "created_at"],
    "generated_test_suites": ["suite_id", "status", "spec_hash", "commit_sha", "created_at"],
    "test_runs": ["run_timestamp", "commit_sha", "passed_tests", "total_tests", "email_sent", "suite_id"],
    "lessons": ["test_name", "status", "lesson"],
    "approvals": ["approval_id", "kind", "status", "suite_id", "previous_suite_id", "decided_at"],
    "notifications": ["attempted_at", "outcome", "recipient", "error"],
}


def short(value, width=34):
    text = "" if value is None else str(value).replace("\n", " ")
    return text if len(text) <= width else text[:width - 3] + "..."


def main():
    argv = sys.argv[1:]
    events = int(argv.pop(argv.index("--events") + 1)) if "--events" in argv else 15
    args = [a for a in argv if not a.startswith("--")]
    root = Path(args[0] if args else ".").resolve()
    db = root / ".spectest" / "spectest.db"
    if not db.exists():
        sys.exit(f"No SpecTest memory at {db}")
    with closing(sqlite3.connect(db)) as conn:
        conn.row_factory = sqlite3.Row
        for table, cols in COLUMNS.items():
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            print(f"\n== {table} ({len(rows)} rows)")
            if rows:
                print("   " + " | ".join(c.ljust(14) for c in cols))
                for row in rows[-8:]:
                    print("   " + " | ".join(short(row[c], 14 if c != "lesson" else 60).ljust(14) for c in cols))
    log = root / ".spectest" / "logs" / "agent.jsonl"
    if log.exists():
        lines = log.read_text(encoding="utf-8").splitlines()
        print(f"\n== last {events} of {len(lines)} action-log events (.spectest/logs/agent.jsonl)")
        for line in lines[-events:]:
            e = json.loads(line)
            details = ", ".join(f"{k}={short(v, 40)}" for k, v in e.items() if k not in ("ts", "event"))
            print(f"   {e['ts'][11:23]}  {e['event']:<22} {details}")


if __name__ == "__main__":
    main()
