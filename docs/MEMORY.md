# SpecTest memory design and lifecycle

SpecTest keeps one SQLite database per project at `<project>/.spectest/spectest.db`. The full schema is in
[`schema.sql`](schema.sql). SQLite is the **authoritative store**. Everything else is derived from it and can be
rebuilt: the visible test file in `spectest_tests/`, the email reports, and `spectest status`. No vector database
is used. The workflow needs exact records (versions, hashes, counts, decisions), not semantic search.

## Memory components (brief terminology)

| Component | In SpecTest | Bounded how |
|---|---|---|
| **Working state** | The LangGraph `AgentState` for one run: current action, spec hash, commit, test counts, failing tests, investigator messages and tool results. Not persisted; a run is short and is simply restarted. A run lock prevents two runs from overlapping. | One run. The investigator is limited to 12 steps, file reads to 300 lines, and pytest output to 8 KB. |
| **Long-term memory** | `spec_baselines`, `generated_test_suites`, `test_runs`, `lessons`, `approvals`, `notifications` | Rows are never overwritten: old suites become `SUPERSEDED`, and lessons/approvals carry a status. |
| **Source knowledge** | The spec file, the project's source code, and `SPECTEST.md`. Read fresh every run, never copied into memory, except the spec text, which is stored in each baseline version for history. | Signatures only for test generation; the investigator reads files on demand. |

## Lifecycle

| Table | What is saved | Why | When it is read | Who can access it | Correction / deletion |
|---|---|---|---|---|---|
| `meta` | `project_id` | Binds the database to one project, so another project can't use it by mistake | Every time memory is opened | SpecTest for this project only | Fixed for the project's life; `spectest remove` deletes it |
| `spec_baselines` | Every spec version: hash, full text, version number | Detect spec changes; keep the history of approved requirements | Start of every run (latest version) | This project | A spec edit creates a new version; older ones are kept |
| `generated_test_suites` | Every generated or repaired suite, with the spec hash and commit it belongs to; exactly one `CURRENT` | Re-run the same approved tests when only the code changes; restore after restarts; give the previous suite to the generator after a spec change | Every run | This project | Spec change or repair: new `CURRENT`, old one `SUPERSEDED`. `spectest reject` restores the pre-repair suite as a new `CURRENT` |
| `test_runs` | Counts (from pytest), failing-test output, the agent's diagnosis, repairs, whether the report was delivered | Decide whether anything changed; history for the investigator; one report per commit | Every run (latest); the investigator gets the last 3 | This project | Append-only |
| `lessons` | Why a generated test was wrong, with the spec quote; status `PENDING` / `APPROVED` / `REJECTED` | Stop the generator from repeating a mistake | Test generation and investigation, **approved lessons only** | This project | Follows the approval decision |
| `approvals` | Each agent test repair: new suite, previous suite, details, status, decision time | Keep the agent's suggestion separate from the developer's decision | `spectest status`, `approve`, `reject` | The developer, via the CLI | `approve` / `reject` sets the status once; never edited afterwards |
| `notifications` | Every report delivery attempt: recipient, approval rule, outcome (`sent` / `saved_to_outbox` / `failed`), error | Record approval, delivery and failure separately; retry failed deliveries without duplicates | Before sending, and by `spectest status` | This project | Append-only |

## Rules that use memory

- **Change detection:** spec hash differs from the `CURRENT` suite's → regenerate. Commit or source hash differs from the last run → re-run the existing suite. Neither → nothing to do, with no LLM call.
- **Restart continuity:** every decision is made from SQLite at the start of the run. A new process continues exactly where the last one stopped, without re-reading or re-uploading anything.
- **Correction:** a spec change creates version N+1, supersedes the old suite, and the next decisions use only the new version. History stays queryable.
- **Approved versions only:** agent repairs are used provisionally, but their lessons influence future generation only after `spectest approve`. A rejected repair is rolled back.
- **Idempotent side effects:** a report is delivered at most once per (commit, suite). A failed delivery is recorded and retried on the next run, without re-running tests or creating a new run record.

## Isolation

- Every project has its own database inside its own folder, bound to its `project_id`. Opening it as a different project raises an error.
- `SPECTEST.md` paths must stay inside the project.
- The agent's read tools refuse `.spectest/`, `.env`, keys, databases, `.git/`, virtualenvs, and anything outside the project.
- The shared settings file (`spectest config`) holds only API keys and SMTP settings, never project data.

## Deletion

`spectest remove` deletes a project's memory (`.spectest/`), generated tests and `SPECTEST.md`, after showing what it
will delete and asking for confirmation. It refuses while a run is active.
