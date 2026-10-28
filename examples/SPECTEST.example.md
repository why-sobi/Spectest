# SpecTest: calculator

SpecTest reads this file at the start of every run. It is this project's own configuration;
other projects have their own SPECTEST.md and their own memory in their own `.spectest/` folder.

## Settings
<!-- `key: value` lines. Paths are relative to this folder and must stay inside it. -->
project_id: calculator               # name used in reports and the generated test file name
spec_path: docs/FEATURE_SPEC.md      # natural-language requirements that tests are generated from
source_dir: src                      # code under test (imported by the generated tests)
exclude:                             # extra folders to ignore, comma-separated (e.g. scripts, migrations)
allow_imports:                       # libraries generated tests may import besides pytest/stdlib (e.g. numpy, PIL)
tests_dir: spectest_tests            # generated pytest files (visible, git-ignored)
workspace_dir: .spectest             # memory database, logs, email outbox, backups (hidden, git-ignored)
report_email:                        # empty = your own address (SMTP_USER from `spectest config`)
email_on: always                     # always | failure | never
max_repairs: 2                       # test fixes the investigator may make per run (0 = diagnose only)

## Test instructions
<!-- Extra rules for test generation, one per line. Changing them regenerates the tests.
     Examples:
     - Focus on edge cases: empty strings, None, negative numbers.
     - Do not test private helpers.
     - Use parametrize for tables of inputs and outputs. -->
-

## What SpecTest reads
- **Spec:** `docs/FEATURE_SPEC.md` (sent to the LLM)
- **For writing tests:** public functions, classes and methods in `src`: signatures and docstrings only,
  never their bodies, so tests follow the spec, not the code. Skips hidden folders, virtualenvs, `tests/`, and anything in `exclude`.
- **For investigating failures:** the investigator agent may read any project file (sent to the LLM provider),
  except `.env`, keys, databases, `.git/`, `.spectest/` and virtualenvs.
- **Memory:** the previous test suite and lessons from past repairs are used when the spec changes.
- **This file:** settings and test instructions

Detected when `spectest init` ran:
```
# module: src.calculator
def add(a: float, b: float) -> float:
...
```

## What SpecTest does
1. Hashes the spec and source on each run; does nothing if neither changed.
2. Spec or test instructions changed: generates a new pytest suite into `spectest_tests/` (old suite kept in memory as SUPERSEDED).
   Generated code is checked first: valid syntax, at least one `test_` function, and only safe imports.
3. Source changed: re-runs the existing suite without calling the LLM.
4. Runs pytest. Pass/fail comes from pytest itself, never from the LLM.
5. On failures, the investigator agent reads the project and runs tests to find out why, classifying each failure
   as CODE BUG (with file:line and a suggested fix), TEST BUG, or SPEC AMBIGUITY.
   It may fix TEST BUGs in the generated test file only, and code enforces the rules: only currently failing
   tests, no deleting or skipping tests, an exact spec quote proving the old test wrong, at most `max_repairs`.
   The suite is then re-run and that run's result is final. Repairs are remembered as lessons.
6. Saves the run in `.spectest/spectest.db` and emails one report per commit (see `email_on`), including
   the diagnosis and any repairs to review.

The memory database is the source of truth for the generated tests: if you edit `spectest_tests/` by hand,
your version is backed up to `.spectest/backups/` and the stored suite is restored on the next run.
SpecTest never edits your source code, your spec, or this file. It only writes to `spectest_tests/` and `.spectest/`.
