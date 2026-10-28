# SpecTest: Quick Reference

## First time
```bash
spectest config                 # add an API key (Groq / Gemini / OpenRouter) + optional Gmail App Password
spectest config --check         # verify keys and email login
spectest config --test-email    # send yourself a test email
```

## Per project
```bash
cd my-project
spectest init               # auto-detects the code folder (a package named like the project, else src/, else packages)
spectest init monocle       # or say which folder(s) hold the code: spectest init pkg_a pkg_b
spectest init --git-hook    # also test every commit automatically (nothing runs between commits)
```
Creates `SPECTEST.md`, `docs/FEATURE_SPEC.md`, `.spectest/` and `spectest_tests/`, and updates `.gitignore`.
1. Describe your functions in `docs/FEATURE_SPEC.md`.
2. In `SPECTEST.md`, check `source_dir` (reports go to your own `SMTP_USER` unless you set `report_email`).
3. `spectest run`.

## Commands
| Command | Does |
|---|---|
| `spectest run` | one check; exit code `0` = all passed, `1` = failures, `2` = error (`--no-memory`: ignore memory, for comparisons) |
| `spectest status` | current state, recommended next action, supporting evidence, pending approvals |
| `spectest approve [id\|all]` / `spectest reject <id>` | accept or undo the agent's test repairs |
| `spectest watch` | runs on every change to the spec, `SPECTEST.md` or `.py` files (Ctrl+C stops) |
| `spectest history` | past runs (`python scripts/inspect_memory.py` shows all memory tables and the action log) |
| `spectest config [--check \| --test-email [addr] \| --path]` | shared settings (keys, email) |
| `spectest init [folders] [--force]` | set up a folder; `folders` = code to test (default: auto-detect) |
| `spectest remove [--yes]` | take SpecTest out of the project (asks first; keeps your edited spec and `.env` rule) |

All commands accept `--root PATH` and work from subfolders.

**Watch or git hook?** `watch` re-tests on every save while its terminal is open; it never survives closing the terminal or a reboot. `init --git-hook` instead tests each commit in the background (the commit returns immediately; output in `.spectest/logs/hook.log`) and nothing runs between commits.

**Background usage:** none. Commands exit when done; only an open `spectest watch` keeps running (~86 MB RAM, no CPU while idle) until you press Ctrl+C or close its terminal. It also stops by itself if SpecTest is removed from the project.

## Writing the spec
```markdown
## divide(a, b)
- Returns `a / b` as a float.
- `divide(7, 2)` returns 3.5.
- Dividing by zero raises `ZeroDivisionError`.
```
Be concrete: one behavior per line, with examples. Anything left unstated isn't tested.

## `SPECTEST.md` settings
| Key | Default | |
|---|---|---|
| `source_dir` | auto-detected | code under test; several folders comma-separated |
| `exclude` | (none) | folders to skip, comma-separated |
| `allow_imports` | (none) | libraries tests may import, e.g. `numpy, PIL` (pytest + safe stdlib always allowed) |
| `report_email` | your `SMTP_USER` | where reports go |
| `email_on` | `always` | `always` / `failure` / `never` |
| `max_repairs` | `2` | test fixes the agent may make per run (`0` = diagnose only) |

`## Test instructions` adds your own rules for test generation, e.g. "use parametrize".

## What happens on a run
| Change | Result |
|---|---|
| nothing | "No changes detected" |
| spec / test instructions | tests regenerated (using the previous suite + past lessons), then run |
| code only | existing tests re-run |
| tests fail | investigator reads the project, reports CODE BUG (file:line + fix + the spec line it breaks) / TEST BUG / SPEC AMBIGUITY, may repair wrong tests, emails you |

The investigator gets 12 steps. With 2 left it's told to wrap up, and on the last step it must call `finish`, so you always get a diagnosis.

## Where things are
| Path | |
|---|---|
| `spectest_tests/` | generated tests: read them, don't edit them (edits are backed up and replaced) |
| `.spectest/logs/agent.jsonl` | everything that happened, including each agent tool call |
| `.spectest/outbox/` | reports, when email isn't set up |
| `%APPDATA%\spectest\.env` / `~/.config/spectest/.env` | API keys + SMTP (`spectest config --path`) |

## Common fixes
| Problem | Fix |
|---|---|
| `All LLM providers failed` | `spectest config --check` |
| `model_not_found` warning | set a current model, e.g. `GROQ_MODEL=...`, via `spectest config` |
| Gmail login rejected | use a 16-letter App Password; `SMTP_HOST=smtp.gmail.com` |
| `ModuleNotFoundError` in tests | give the project a `.venv`/`venv` with its dependencies + `pytest`, or set `python:` |
| tests rejected with `Disallowed import: numpy` | add it to `allow_imports` in `SPECTEST.md` |
| `still the template` | write your spec |

Full details: [README.md](README.md).
