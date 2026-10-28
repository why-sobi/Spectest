-- SpecTest memory schema (SQLite), one database per project at .spectest/spectest.db.
-- Created by `spectest init` (spectest/scaffold.py -> spectest.memory.Memory), which also binds the database
-- to the project's project_id in the meta table. Opening an existing database applies these migrations:
--   test_runs: add failure_analysis TEXT, repairs TEXT
--   lessons: add approval_id TEXT, status TEXT DEFAULT 'APPROVED'

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
