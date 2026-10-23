"""`spectest init`: sets up SpecTest in a project folder without overwriting anything."""
import re
import subprocess
from pathlib import Path

from spectest.config import CONFIG_FILE, GLOBAL_ENV, load_config, migrate_global_env
from spectest.memory import Memory
from spectest.tools.spec_reader import extract_signatures, is_skipped, source_files

SPECTEST_TEMPLATE = """# SpecTest: {name}

SpecTest reads this file at the start of every run. It is this project's own configuration;
other projects have their own SPECTEST.md and their own memory in their own `.spectest/` folder.

## Settings
<!-- `key: value` lines. Paths are relative to this folder and must stay inside it. -->
{project_id_kv}# name used in reports and the generated test file name
spec_path: docs/FEATURE_SPEC.md      # natural-language requirements that tests are generated from
{source_dir_kv}# code under test (imported by the generated tests)
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
- **For writing tests:** public functions, classes and methods in `{source_dir}`: signatures and docstrings only,
  never their bodies, so tests follow the spec, not the code. Skips hidden folders, virtualenvs, `tests/`, and anything in `exclude`.
- **For investigating failures:** the investigator agent may read any project file (sent to the LLM provider),
  except `.env`, keys, databases, `.git/`, `.spectest/` and virtualenvs.
- **Memory:** the previous test suite and lessons from past repairs are used when the spec changes.
- **This file:** settings and test instructions

Detected when `spectest init` ran:
```
{signatures}
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
"""

SPEC_TEMPLATE = """# {name} Feature Specification

Describe each function's expected behavior in plain language. SpecTest turns this into pytest tests.

## function_name(arg1, arg2)
- Returns ...
- Raises `ValueError` when ...
"""

ENV_TEMPLATE = """# LLM providers (tried in this order; any missing key is skipped)
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-oss-120b

# Email reports. Gmail / Google Workspace: host smtp.gmail.com, port 587, and an App Password
# (https://myaccount.google.com/apppasswords), not your normal password.
# If unset, reports are written to .spectest/outbox/ instead. Test with: spectest config --test-email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
"""


def _write_if_missing(path: Path, content: str, created: list[str]):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(str(path))


GITIGNORE_HEADER = "# SpecTest (spectest init)"


def ensure_gitignore(root: Path, entries: list[str]) -> list[str]:
    """Create .gitignore or append the missing entries. Returns the entries added."""
    path = root / ".gitignore"
    text = path.read_bytes().decode("utf-8", errors="replace") if path.exists() else ""  # raw: keep \r\n visible
    present = {ln.strip().strip("/") for ln in text.splitlines()}  # `/x/`, `x/`, `x` all count as present
    missing = [e for e in entries if e.strip("/") not in present]
    if missing:
        newline = "\r\n" if "\r\n" in text else "\n"  # keep the file's existing line endings
        block = newline.join([GITIGNORE_HEADER, *missing]) + newline
        prefix = "" if not text else (newline if text.endswith(("\n", "\r")) else newline * 2)
        with open(path, "a", encoding="utf-8", newline="") as f:
            f.write(prefix + block)
    return missing


def tracked_by_git(root: Path, entries: list[str]) -> list[str]:
    """Entries that git already tracks (.gitignore does not untrack them)."""
    try:
        out = subprocess.run(["git", "ls-files", "--", *[e.strip("/") for e in entries]],
                             cwd=root, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return sorted({line.split("/")[0] for line in out.splitlines() if line})


NOT_SOURCE = {"tests", "test", "docs", "doc", "examples", "scripts", "bench", "benchmarks", "build", "dist"}


def detect_source_dirs(root: Path) -> list[str]:
    """Best guess at the code under test, relative to root.

    A package named after the project wins (e.g. Monocle/monocle), then `src/` if it holds Python code,
    then every top-level package, then the project folder itself.
    """
    exclude = frozenset({".spectest", "spectest_tests"})
    packages = sorted(d.name for d in root.iterdir()
                      if d.is_dir() and (d / "__init__.py").is_file()
                      and not is_skipped((d.name,), exclude) and d.name.lower() not in NOT_SOURCE)
    own_name = re.sub(r"\W+", "_", root.name).strip("_").lower()
    if own_name in packages:
        return [own_name]
    if (root / "src").is_dir() and source_files(root / "src", exclude):
        return ["src"]
    return packages or ["."]


def init_project(root: Path | str = ".", force: bool = False,
                 folders: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Returns (created, warnings). Raises ValueError for folders that must not be initialized.

    `folders` are the source folders to test (default: auto-detected).
    """
    root = Path(root).resolve()
    if not force and (root == Path.home().resolve() or root == Path(root.anchor)):
        raise ValueError(f"Refusing to set up SpecTest in {root} (home or drive root): it would scan every file "
                         f"below it. cd into a project folder, or pass --force.")
    created: list[str] = []
    warnings: list[str] = []

    parent = next((p for p in root.parents if (p / CONFIG_FILE).is_file()), None)
    if parent and not (root / CONFIG_FILE).exists():
        warnings.append(f"{root.name} is inside another SpecTest project ({parent}). "
                        f"It gets its own separate config and memory.")

    if folders:
        for f in folders:
            path = (root / f).resolve()
            if not path.is_relative_to(root) or not path.is_dir():
                raise ValueError(f"source folder {f!r} is not a folder inside {root}")
        folders = [(root / f).resolve().relative_to(root).as_posix() or "." for f in folders]
        if (root / CONFIG_FILE).exists():
            warnings.append(f"{CONFIG_FILE} already exists, so the folders you passed were not applied; "
                            f"set `source_dir: {', '.join(folders)}` in it yourself.")
    source_dirs = folders or detect_source_dirs(root)
    source_dir = ", ".join(source_dirs)
    project_id = re.sub(r"\W+", "_", root.name).strip("_").lower() or "project"
    exclude = frozenset({".spectest", "spectest_tests"})
    signatures = (extract_signatures([root / d for d in source_dirs], root, exclude, docstrings=False).strip()
                  or "(no Python files found yet)")
    _write_if_missing(root / CONFIG_FILE, SPECTEST_TEMPLATE.format(
        name=root.name, source_dir=source_dir, signatures=signatures,
        project_id_kv=f"project_id: {project_id}".ljust(37), source_dir_kv=f"source_dir: {source_dir}".ljust(37)),
        created)
    _write_if_missing(root / "docs" / "FEATURE_SPEC.md", SPEC_TEMPLATE.format(name=root.name), created)
    migrate_global_env()
    _write_if_missing(GLOBAL_ENV, ENV_TEMPLATE, created)

    cfg = load_config(root)  # honors any custom paths in an existing SPECTEST.md
    cfg.tests_dir.mkdir(parents=True, exist_ok=True)
    if not cfg.db_path.exists():
        Memory(cfg.db_path).close()  # creates the schema
        created.append(str(cfg.db_path))

    added = ensure_gitignore(root, cfg.gitignore_entries)
    if added:
        created.append(f"{root / '.gitignore'} (+ {', '.join(added)})")
    tracked = tracked_by_git(root, cfg.gitignore_entries)
    if tracked:
        warnings.append(f"git already tracks {', '.join(tracked)}; .gitignore won't hide it until you run: "
                        f"git rm -r --cached {' '.join(tracked)}")
    return created, warnings
