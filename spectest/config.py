"""Loads the project's SPECTEST.md (settings + test instructions) and .env secrets."""
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def config_dir() -> Path:
    """The OS's standard per-user config folder: %APPDATA%\\spectest on Windows, ~/.config/spectest elsewhere.

    SPECTEST_CONFIG_DIR overrides it (the evaluation uses this so it never sees your real keys or email).
    """
    if os.getenv("SPECTEST_CONFIG_DIR"):
        return Path(os.environ["SPECTEST_CONFIG_DIR"])
    if sys.platform == "win32" and os.getenv("APPDATA"):
        return Path(os.environ["APPDATA"]) / "spectest"
    return Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config") / "spectest"


# Shared API keys for every project; a project's own .env takes precedence.
GLOBAL_ENV = config_dir() / ".env"
LEGACY_GLOBAL_ENV = Path.home() / ".spectest" / ".env"  # used before `spectest config` existed
CONFIG_FILE = "SPECTEST.md"


def migrate_global_env():
    """Move keys from the old ~/.spectest/.env to the standard location (once)."""
    if LEGACY_GLOBAL_ENV.is_file() and not GLOBAL_ENV.exists():
        GLOBAL_ENV.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(LEGACY_GLOBAL_ENV), GLOBAL_ENV)
        try:
            LEGACY_GLOBAL_ENV.parent.rmdir()  # only if now empty
        except OSError:
            pass
        print(f"[spectest] moved your keys from {LEGACY_GLOBAL_ENV} to {GLOBAL_ENV}", file=sys.stderr)
EMAIL_MODES = ("always", "failure", "never")


@dataclass
class Config:
    root: Path
    config_file: Path
    project_id: str
    spec_path: Path
    source_dirs: list[Path]  # one or more folders with the code under test
    workspace: Path       # hidden: memory, logs, outbox, backups
    tests_dir: Path       # visible: generated pytest files
    report_email: str
    python: str
    email_on: str = "always"
    max_repairs: int = 2  # test fixes the investigator may make per run (0 = diagnose only)
    exclude: frozenset[str] = field(default_factory=frozenset)
    test_instructions: str = ""
    allow_imports: frozenset[str] = field(default_factory=frozenset)  # extra libraries tests may import

    @property
    def db_path(self) -> Path:
        return self.workspace / "spectest.db"

    @property
    def logs_dir(self) -> Path:
        return self.workspace / "logs"

    @property
    def test_file(self) -> Path:
        return self.tests_dir / f"test_{self.project_id}_spec.py"

    @property
    def gitignore_entries(self) -> list[str]:
        """Everything SpecTest creates in the project, anchored to the project folder."""
        return [f"/{self.workspace.relative_to(self.root).as_posix()}/",
                f"/{self.tests_dir.relative_to(self.root).as_posix()}/",
                f"/{CONFIG_FILE}", ".env"]

    def wants_email(self, failed: int) -> bool:
        return self.email_on == "always" or (self.email_on == "failure" and failed > 0)


def is_placeholder_email(addr: str) -> bool:
    addr = (addr or "").strip().lower()
    return "@" not in addr or addr.endswith(("@example.com", "@example.org"))


def find_project_root(start: Path | str = ".") -> Path:
    """Nearest folder at or above `start` containing SPECTEST.md (like git finds .git)."""
    start = Path(start).resolve()
    for folder in (start, *start.parents):
        if (folder / CONFIG_FILE).is_file():
            return folder
    raise FileNotFoundError(f"No {CONFIG_FILE} found in {start} or any parent folder. Run `spectest init` first.")


def find_python(root: Path) -> str:
    """Prefer the project's own venv (so tests see its dependencies) if it has pytest; else SpecTest's Python."""
    candidates = [root / venv / sub for venv in (".venv", "venv", "env")
                  for sub in (Path("Scripts") / "python.exe", Path("bin") / "python")]
    for candidate in candidates:
        if candidate.exists():
            ok = subprocess.run([str(candidate), "-c", "import pytest"], capture_output=True).returncode == 0
            if ok:
                return str(candidate)
    return sys.executable


def md_section(text: str, heading: str) -> str | None:
    """Body of a `## heading` section (up to the next `## `), or None if absent."""
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return match.group(1) if match else None


def parse_settings(text: str) -> dict[str, str]:
    body = md_section(text, "Settings") or ""
    settings = {}
    for key, value in re.findall(r"^(\w+):[ \t]*(.*?)[ \t]*$", body, re.M):
        value = re.sub(r"(^|\s)#.*$", "", value).strip()  # allow trailing `# comment`
        if value:
            settings[key] = value
    return settings


def parse_instructions(text: str) -> str:
    body = md_section(text, "Test instructions") or ""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)  # template hints are comments
    lines = [ln.rstrip() for ln in body.strip().splitlines()]
    return "\n".join(ln for ln in lines if ln.strip() not in ("", "-"))


def _inside(root: Path, value: str, key: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"{CONFIG_FILE}: {key} must be inside the project folder, got {value!r}")
    return path


def load_config(start: Path | str = ".") -> Config:
    root = find_project_root(start)
    load_dotenv(root / ".env")
    migrate_global_env()
    load_dotenv(GLOBAL_ENV)  # does not override values already set

    config_file = root / CONFIG_FILE
    text = config_file.read_text(encoding="utf-8", errors="replace")
    settings = parse_settings(text)
    email_on = settings.get("email_on", "always").lower()
    if email_on not in EMAIL_MODES:
        raise ValueError(f"{CONFIG_FILE}: email_on must be one of {', '.join(EMAIL_MODES)}")

    source_dirs = []
    for value in [v.strip() for v in settings.get("source_dir", ".").split(",") if v.strip()] or ["."]:
        folder = _inside(root, value, "source_dir")
        if not folder.is_dir():
            raise FileNotFoundError(f"{CONFIG_FILE}: source_dir {value!r} does not exist")
        source_dirs.append(folder)
    workspace = _inside(root, settings.get("workspace_dir", ".spectest"), "workspace_dir")
    tests_dir = _inside(root, settings.get("tests_dir", "spectest_tests"), "tests_dir")
    if root in (workspace, tests_dir) or workspace == tests_dir:
        raise ValueError(f"{CONFIG_FILE}: workspace_dir and tests_dir must be separate sub-folders")

    try:
        max_repairs = max(0, int(settings.get("max_repairs", "2")))
    except ValueError:
        raise ValueError(f"{CONFIG_FILE}: max_repairs must be a whole number")
    user_exclude = {x.strip().strip("/\\") for x in settings.get("exclude", "").split(",") if x.strip()}
    return Config(
        root=root,
        config_file=config_file,
        project_id=re.sub(r"\W+", "_", settings.get("project_id", root.name)).strip("_").lower() or "project",
        spec_path=_inside(root, settings.get("spec_path", "docs/FEATURE_SPEC.md"), "spec_path"),
        source_dirs=source_dirs,
        workspace=workspace,
        tests_dir=tests_dir,
        # empty or placeholder -> your own address from `spectest config` (SMTP_USER)
        report_email=(settings.get("report_email", "") if not is_placeholder_email(settings.get("report_email", ""))
                      else os.getenv("SMTP_USER", "").strip()),
        python=settings.get("python") or find_python(root),
        email_on=email_on,
        max_repairs=max_repairs,
        # SpecTest's own folders are never treated as source code.
        exclude=frozenset(user_exclude | {workspace.name, tests_dir.name}),
        test_instructions=parse_instructions(text),
        allow_imports=frozenset(x.strip() for x in settings.get("allow_imports", "").split(",") if x.strip()),
    )
