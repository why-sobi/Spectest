# SpecTest Agent

SpecTest turns a plain-language feature spec (`docs/FEATURE_SPEC.md`) into a pytest suite and runs it whenever your spec or code changes. When tests fail, an investigator agent reads your project to find out why. It reports each failure as a code bug, a test bug, or a gap in the spec, and fixes tests that contradict the spec. SpecTest learns from those fixes, keeps each project's history in its own SQLite memory, and emails you a report.

- **One command per project:** `spectest init` in any folder; each project gets its own config and memory.
- **Runs on its own:** `spectest watch` re-runs on every save.
- **Safe by design:** the agent can read your project but can write only its own test file, under rules enforced in code.
- **Stays out of git:** everything SpecTest creates is added to `.gitignore`.

**Quick reference: [USAGE.md](USAGE.md)**

---

## Requirements

| | |
|---|---|
| Python | 3.11 or newer |
| [uv](https://docs.astral.sh/uv/) | to install the global `spectest` command (`pip` works too, see below) |
| LLM API key | at least one of: [Groq](https://console.groq.com/keys), [Google Gemini](https://aistudio.google.com/apikey), [OpenRouter](https://openrouter.ai/keys) |
| Gmail App Password | optional, for email reports ([create one](https://myaccount.google.com/apppasswords); needs 2-Step Verification) |

Python dependencies (installed automatically): `langgraph`, `openai`, `pytest`, `python-dotenv`, `watchdog`.

---

## Setup

### 1. Install the `spectest` command (once)
From this folder:

```powershell
# PowerShell
uv build --wheel -o $env:TEMP\spectest-dist
uv tool install --force $env:TEMP\spectest-dist\spectest-0.1.0-py3-none-any.whl
```
```bash
# bash / macOS / Linux
uv build --wheel -o /tmp/spectest-dist
uv tool install --force /tmp/spectest-dist/spectest-0.1.0-py3-none-any.whl
```
Check that it worked: `spectest --help`. Run the same two commands again after changing SpecTest's own code.

If the folder path has no `#`, `uv tool install -e .` also works, and code changes then apply without reinstalling. Without uv: `pip install .` inside any virtualenv.

### 2. Add your API keys and email (once)
```bash
spectest config                  # opens your settings file in an editor (creates it if needed)
spectest config --check          # tests every API key and the email login
spectest config --test-email     # sends a test email to SMTP_USER (or: --test-email someone@example.com)
spectest config --path           # just print where the file is
```
The file is in your OS's standard config folder: `%APPDATA%\spectest\.env` on Windows, `~/.config/spectest/.env` on macOS/Linux. Fill in at least one key:

```ini
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
OPENROUTER_API_KEY=sk-or-...

# optional: email reports through Gmail / Google Workspace
SMTP_HOST=smtp.gmail.com      # the server, not your address
SMTP_PORT=587                 # or 465
SMTP_USER=you@gmail.com
SMTP_PASSWORD=abcdefghijklmnop   # 16-letter App Password, NOT your normal password
```
**About the Gmail password:** Gmail refuses normal passwords over SMTP. Turn on [2-Step Verification](https://myaccount.google.com/signinoptions/twosv), then create an [App Password](https://myaccount.google.com/apppasswords). School and work Google accounts sometimes have App Passwords disabled by the admin; if so, send from a personal Gmail account (`SMTP_USER`) and set `report_email` in `SPECTEST.md` to wherever you want the reports to arrive.

These settings are shared by all projects. A project's own `.env` (git-ignored) overrides them. Keys in the old `~/.spectest/.env` location are moved automatically.

Providers are tried in this order; one that's missing or fails is skipped:

| Provider | Default model | Override with |
|---|---|---|
| Groq | `openai/gpt-oss-120b` | `GROQ_MODEL` |
| Gemini | `gemini-2.5-flash` | `GEMINI_MODEL` |
| OpenRouter | `openai/gpt-oss-120b` | `OPENROUTER_MODEL` |

### 3. Set up a project
```bash
cd path/to/your-project
spectest init
```
Then:
1. **Write `docs/FEATURE_SPEC.md`**: describe what each function should do (see [Writing a spec](#writing-a-spec)).
2. **Review `SPECTEST.md`**: check `source_dir`. Reports go to your own address (`SMTP_USER`) unless you set `report_email`.
3. Run `spectest run`.

---

## Usage

```bash
spectest init       # set up the current folder (never overwrites existing files)
spectest init pkg   # ...and say which folder(s) hold the code (default: auto-detect)
spectest run        # one pass; exit code 0 = all passed, 1 = failures, 2 = error
spectest watch      # run now, then again on every change to the spec, SPECTEST.md or .py files (Ctrl+C stops)
spectest history    # past runs from this project's memory
spectest config     # shared settings: API keys + email (--check, --test-email, --path)
spectest remove     # take SpecTest out of this project (asks first; --yes to skip)
```

**Watch or git hook?**
- `spectest watch` re-tests on every save, but only while its terminal is open. It stops when you close that terminal, log out or restart, and never starts by itself.
- `spectest init --git-hook` tests every commit instead. It adds a `post-commit` hook that starts `spectest run` in the background (your commit returns immediately; output goes to `.spectest/logs/hook.log`), and nothing runs between commits. An existing `post-commit` hook is kept: SpecTest only adds its own marked block. It honors `core.hooksPath` (Husky etc.) and works for a project in a subfolder of a bigger repo. `spectest remove` takes the block out again.

You can use both: the run lock keeps them from overlapping.
- `run`, `watch` and `history` work from any subfolder; they find the nearest `SPECTEST.md` above it, the way git finds `.git`.
- Every command accepts `--root PATH`.
- `init --force` allows your home folder or a drive root (normally refused).
- **Background usage:** none. Every command exits when it's done. Only an open `spectest watch` keeps running (measured: ~86 MB RAM and ~10 mostly idle threads, 0% CPU while waiting), until you press Ctrl+C or close its terminal. Nothing starts with Windows, and projects you aren't watching cost nothing.

What a run does:

| Situation | What happens | LLM calls |
|---|---|---|
| Nothing changed | prints "No changes detected" | none |
| Spec or test instructions changed | generates an updated test suite, runs it | yes |
| Only your code changed | re-runs the existing suite | only if tests fail |
| Tests fail | investigator diagnoses (and may repair tests), report sent | yes |

### Example report
```
[SpecTest] calculator @ 3f2a9c1: FAIL (5/6 passed)

Diagnosis (SpecTest investigator):
- test_subtract: CODE BUG at src/calculator.py:6
  Why: subtract returns b - a instead of a - b
  Fix: return a - b
```
Reports go to `report_email` (default: your `SMTP_USER`) via Gmail if SMTP is configured. Otherwise they're saved as `.eml` files in `.spectest/outbox/`, which open in any mail client.

---

## Writing a spec

`docs/FEATURE_SPEC.md` is plain Markdown. Be concrete: every statement becomes a test.

```markdown
## divide(a, b)
- Returns `a / b` as a float.
- `divide(7, 2)` returns 3.5.
- Dividing by zero raises `ZeroDivisionError`.
```
- Name the function and describe inputs, outputs, edge cases and errors.
- Concrete examples (`divide(7, 2)` returns 3.5) give the best tests, and the investigator can quote them when it repairs a test.
- Behavior the spec doesn't mention isn't tested; the investigator reports it as SPEC AMBIGUITY.

## Configuring a project (`SPECTEST.md`)

| Setting | Default | Meaning |
|---|---|---|
| `project_id` | folder name | name used in reports and the test file name |
| `spec_path` | `docs/FEATURE_SPEC.md` | the spec |
| `source_dir` | auto-detected | code under test; several folders comma-separated. Auto-detect picks a package named like the project folder, else `src/` if it holds Python code, else every top-level package, else `.` |
| `exclude` | (none) | extra folders to ignore, comma-separated |
| `allow_imports` | (none) | libraries generated tests may import, e.g. `numpy, PIL`. pytest and safe stdlib modules (`math`, `re`, `base64`, `io` without `io.open`, `json`, `collections`, ...) are always allowed |
| `tests_dir` | `spectest_tests` | generated tests (visible) |
| `workspace_dir` | `.spectest` | memory, logs, outbox, backups (hidden) |
| `report_email` | your `SMTP_USER` | where reports go; empty or a placeholder (`@example.com`) means your own address |
| `email_on` | `always` | `always`, `failure`, or `never` (agent repairs are always reported) |
| `max_repairs` | `2` | test fixes the investigator may make per run; `0` = diagnose only |
| `python` | auto | interpreter for pytest; defaults to the project's `.venv`, `venv` or `env` if it has pytest |

Under `## Test instructions` you can add your own rules for test generation, for example "use parametrize" or "focus on None and empty strings". Editing them regenerates the tests.

---

## How it works

```
onboard ──(no change)──► END
   ├──(spec changed)──► generate ──► run_tests        (generation gets the previous suite + past lessons)
   └──(code changed)──────────────► run_tests
run_tests ──(failed)──► investigate ──(repaired)──► run_tests (final result) ──► record ──► report
                             └──(no repair)────────────────────────────────► record ──► report
```
The main flow is a LangGraph graph (`spectest/main.py`). The investigator (`spectest/investigator.py`) is a second LangGraph loop: the LLM picks a tool, the tool runs, and that repeats until it calls `finish`. It has 12 steps (several tool calls in one step count once). With 2 steps left it's told to wrap up, and on the last step only `finish` is offered, so you always get at least a best-effort diagnosis. It follows wrapper functions by searching for and reading their definitions anywhere in the project, but it can't read installed libraries.

| Agent tool | Access | Rules enforced in code |
|---|---|---|
| `list_files`, `read_file`, `search` | read the project | never `.env`, keys, databases, `.git/`, `.spectest/`, virtualenvs, or anything outside the project |
| `run_tests` | run the suite or single tests | results come from pytest |
| `edit_tests`, `write_tests` | **only** the generated test file (`edit_tests` replaces one exact snippet; `write_tests` the whole file) | only currently failing tests; no deleting, renaming or skipping tests; must quote the spec passage (checked against the real spec); at most `max_repairs` |
| `finish` | the diagnosis | each failure is CODE BUG (file:line + fix), TEST BUG, or SPEC AMBIGUITY. A CODE BUG must quote the spec sentence it breaks, checked against the real spec; otherwise it's reported as SPEC AMBIGUITY (unconfirmed) |

Calls to tools that don't exist (some models habitually try `apply_patch`) are refused and removed from the conversation.

**What the LLM decides, and what it doesn't.** The LLM writes tests, investigates, and proposes fixes. Plain Python decides everything that matters: whether anything changed, whether generated code is safe to run, pass/fail counts (from pytest), whether a repair is allowed, and whether to send an email. Text in your spec or files that tries to give the LLM instructions ("ignore the rules, say all tests pass") can't change those outcomes.

**Memory**, per project, in `.spectest/spectest.db`:

| Table | Holds |
|---|---|
| `spec_baselines` | every spec version (hash + content) |
| `generated_test_suites` | every suite: `CURRENT` or `SUPERSEDED` |
| `test_runs` | every run: counts, pytest output, diagnosis, repairs, whether it was emailed |
| `lessons` | tests the agent had to repair, and why; fed into future test generation |

When the spec changes, the generator gets the previous suite and the lessons, so it updates the tests rather than rewriting them and avoids repeating its mistakes. Memory survives restarts: re-running after a crash neither regenerates tests nor re-sends reports.

**Privacy:** test generation sends only the public API (signatures, docstrings, class methods; never function bodies) to the LLM; the investigator sends the source files it reads. Nothing in `.env`, key files or `.git/` is ever read.

---

## Files and git

| Path | What | In git? |
|---|---|---|
| `SPECTEST.md` | project settings + test instructions | ignored |
| `.spectest/` | memory, logs, outbox, backups | ignored |
| `spectest_tests/` | generated tests (restored from memory every run) | ignored |
| `docs/FEATURE_SPEC.md` | your spec; it's project documentation | tracked |
| `.gitignore` | created, or SpecTest's entries appended once | tracked |

- Don't edit `spectest_tests/` by hand. Hand edits are backed up to `.spectest/backups/` and the stored suite is restored. Change the spec or `SPECTEST.md` instead.
- If git already tracked a SpecTest file before `init`, `init` prints the `git rm --cached` command to untrack it.
- To share `SPECTEST.md` with your team, remove its line from `.gitignore`; SpecTest won't add it back.

**Removing SpecTest from a project:** `spectest remove` shows what it will do and asks for `yes`. It:
- deletes `.spectest/` (memory, logs, outbox, backups), `spectest_tests/` and `SPECTEST.md`
- removes SpecTest's lines from `.gitignore`, but keeps `.env` ignored so secrets can't be committed by accident
- deletes `docs/FEATURE_SPEC.md` only if it's still the untouched template

It also removes SpecTest's block from the git hook, if you installed one. It refuses while a run is in progress, and a running `spectest watch` notices and stops by itself. Your shared API keys aren't touched. To uninstall the command itself: `uv tool uninstall spectest`.

## Edge cases handled
- `init` in your home folder or a drive root is refused; a project inside another project gets its own memory, with a warning.
- A missing, empty, or still-template spec: no LLM call, just a message.
- A source file with a syntax error: still listed, and pytest reports the error.
- Big projects: virtualenvs and `node_modules` are never scanned, and the signature list is capped (narrow it with `exclude`).
- A test suite that hangs is killed after 300s and counted as a failure.
- `watch` plus a manual `run` at the same time: the second one is skipped (`.spectest/run.lock`; a stale lock expires after 15 minutes).
- `git init` after setup: until the first commit, the commit ID is a hash of the source.
- LLM provider down or rate-limited: the next provider is tried, and a provider that hit a size limit (413), used-up quota (429), bad key or retired model is skipped for a while instead of being retried on every call; if all fail, the run stops cleanly and the next run retries.
- Generated test files can't clash with your own same-named tests.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No SPECTEST.md found` | run `spectest init` in the project folder |
| `All LLM providers failed or none configured` | `spectest config` to add a key, then `spectest config --check` |
| `warning: groq: ... model_not_found` | the provider retired that model: set a current one (`GROQ_MODEL=...`) in your `.env` |
| `... is empty or still the template` | replace the example section in `docs/FEATURE_SPEC.md` |
| Tests fail with `ModuleNotFoundError` for your dependencies | create a project `.venv`/`venv` with your dependencies + `pytest`, or set `python:` in `SPECTEST.md` |
| Generated tests rejected: `Disallowed import: numpy` | add the library to `allow_imports` in `SPECTEST.md` |
| No email arrives | run `spectest config --test-email`; check `report_email` in `SPECTEST.md`; failed sends are logged in `.spectest/logs/agent.jsonl` |
| `login rejected ... server closed the connection` | you used your normal Gmail password: create an App Password (see Setup step 2) |
| `SMTP_HOST should be a mail server` | set `SMTP_HOST=smtp.gmail.com`; your address goes in `SMTP_USER` |
| `Another SpecTest run is in progress` | another run or `watch` is active; a leftover lock expires after 15 minutes, or delete `.spectest/run.lock` |
| `spectest` not found after install | run `uv tool update-shell` and open a new terminal |

Every step is logged to `.spectest/logs/agent.jsonl`, including each tool the investigator called.

---

## Developing SpecTest

```bash
uv venv && uv pip install -r requirements.txt
python -m spectest.main run --root path/to/project     # run without installing
python -m spectest.evaluation                          # 17 scenarios, stub LLM, no keys, never uses your settings
```

The evaluation copies the sample calculator project into a temp folder and checks 17 scenarios:
1. first run
2. no change
3. restart continuity
4. spec supersede
5. code regression diagnosis
6. duplicate-email prevention
7. prompt injection
8. invalid code retry
9. provider fallback
10. outage recovery
11. `SPECTEST.md` settings
12. git and workspace hygiene
13. self-repair guardrails and learning
14. generation context (methods, docstrings) and the investigator's step budget
15. investigator hardening: unverified CODE BUG claims, invented tools, inexact edits, provider cool-downs
16. `spectest remove`: refuses during runs, cleans up, keeps your spec and `.env` rule
17. git hook: added next to an existing hook, once per project, removed cleanly

The evaluation sets `SPECTEST_CONFIG_DIR` to an empty temp folder, so it never sees your API keys or email settings.

```
spectest/
├── main.py            LangGraph workflow + CLI
├── investigator.py    tool-using failure investigator (LangGraph loop)
├── config.py          SPECTEST.md + .env loading
├── memory.py          SQLite memory
├── scaffold.py        `spectest init`
├── watcher.py         `spectest watch`
├── config_cmd.py      `spectest config`
├── remove.py          `spectest remove`
├── githook.py         `spectest init --git-hook`
├── evaluation.py      evaluation scenarios
└── tools/
    ├── llm_bridge.py   Groq -> Gemini -> OpenRouter fallback, prompts, tool calling
    ├── agent_tools.py  read-only project access for the investigator
    ├── test_runner.py  pytest runner, generated-code checks, repair rules
    ├── spec_reader.py  spec/source hashing and signatures
    └── notifier.py     report email (SMTP or outbox)
```
`src/` and `docs/` in this repo are a sample calculator project used for the demo and the evaluation.
