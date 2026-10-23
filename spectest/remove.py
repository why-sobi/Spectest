"""`spectest remove`: take SpecTest out of a project, undoing what `spectest init` set up."""
import shutil
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from spectest import githook
from spectest.config import CONFIG_FILE, Config, load_config
from spectest.scaffold import GITIGNORE_HEADER, SPEC_TEMPLATE

STALE_LOCK_SECONDS = 15 * 60  # same rule as main.acquire_lock


def plan(cfg: Config) -> dict:
    """What `remove` would delete and keep, without touching anything."""
    runs = 0
    if cfg.db_path.exists():
        try:
            with closing(sqlite3.connect(cfg.db_path)) as conn:  # closed, or Windows can't delete the file
                runs = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
        except sqlite3.Error:
            pass
    spec_is_template = (cfg.spec_path.is_file() and cfg.spec_path.read_text(encoding="utf-8", errors="replace")
                        == SPEC_TEMPLATE.format(name=cfg.root.name))
    delete = [p for p in (cfg.workspace, cfg.tests_dir, cfg.config_file) if p.exists()]
    if spec_is_template:
        delete.append(cfg.spec_path)
    keep = [cfg.spec_path] if cfg.spec_path.is_file() and not spec_is_template else []
    return {"delete": delete, "keep": keep, "runs": runs}


def run_in_progress(cfg: Config) -> bool:
    lock = cfg.workspace / "run.lock"
    return lock.exists() and time.time() - lock.stat().st_mtime < STALE_LOCK_SECONDS


def clean_gitignore(root: Path, entries: list[str]) -> list[str]:
    """Remove SpecTest's lines from .gitignore (keeping `.env`, which may protect your secrets). Returns them."""
    path = root / ".gitignore"
    if not path.exists():
        return []
    text = path.read_bytes().decode("utf-8", errors="replace")
    newline = "\r\n" if "\r\n" in text else "\n"
    ours = {e.strip("/") for e in entries if e != ".env"}
    kept, removed = [], []
    for line in text.splitlines():
        if line.strip() == GITIGNORE_HEADER or line.strip().strip("/") in ours:
            removed.append(line.strip())
            if line.strip() == GITIGNORE_HEADER and kept and not kept[-1].strip():
                kept.pop()  # the blank line `init` put before its block
        else:
            kept.append(line)
    if removed:
        while kept and not kept[-1].strip():  # drop blank lines left at the end of the block
            kept.pop()
        path.write_bytes((newline.join(kept) + newline if kept else "").encode("utf-8"))
    return removed


def remove_project(cfg: Config) -> list[str]:
    """Delete SpecTest's files from the project. Returns a description of each change."""
    done = []
    for path in plan(cfg)["delete"]:
        # Paths come from SPECTEST.md, which load_config already confined to the project folder.
        if path == cfg.root or not path.resolve().is_relative_to(cfg.root):
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        done.append(f"deleted {path.relative_to(cfg.root).as_posix()}")
    docs = cfg.spec_path.parent
    if docs != cfg.root and docs.is_dir() and not any(docs.iterdir()):
        docs.rmdir()
        done.append(f"deleted empty {docs.relative_to(cfg.root).as_posix()}/")
    removed = clean_gitignore(cfg.root, cfg.gitignore_entries)
    if removed:
        done.append(f"removed from .gitignore: {', '.join(removed)}")
    hook = githook.remove_hook(cfg.root)
    if hook:
        done.append(f"removed SpecTest's block from the git hook {hook}")
    return done


def run(args) -> int:
    try:
        cfg = load_config(args.root)
    except FileNotFoundError:
        print(f"Nothing to remove: no {CONFIG_FILE} in {Path(args.root).resolve()} or its parents.")
        return 0
    if run_in_progress(cfg) and not args.force:
        print("A SpecTest run or `spectest watch` is active for this project. Stop it first (or pass --force).")
        return 2

    p = plan(cfg)
    print(f"Remove SpecTest from {cfg.root}?")
    for path in p["delete"]:
        extra = f" (memory: {p['runs']} recorded runs, logs, outbox, backups)" if path == cfg.workspace else ""
        print(f"  delete  {path.relative_to(cfg.root).as_posix()}{extra}")
    print("  edit    .gitignore (SpecTest's lines; `.env` stays ignored)")
    if githook.has_hook(cfg.root):
        print("  edit    git post-commit hook (SpecTest's block only)")
    for path in p["keep"]:
        print(f"  keep    {path.relative_to(cfg.root).as_posix()} (your spec)")
    print("  keep    your API keys and email settings (shared by all projects: `spectest config --path`)")

    if not args.yes:
        try:
            answer = input("Type 'yes' to remove: ").strip().lower()
        except EOFError:
            answer = ""
        if answer != "yes":
            print("Cancelled; nothing was changed. (Use --yes to skip this question.)")
            return 1
    for line in remove_project(cfg):
        print(f"  {line}")
    print("SpecTest removed from this project. To uninstall the command itself: uv tool uninstall spectest")
    return 0
