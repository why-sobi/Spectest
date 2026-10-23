"""Optional git post-commit hook: run SpecTest once per commit instead of keeping `spectest watch` open.

The hook starts `spectest run` in the background (the commit returns immediately); the run exits when done.
Existing hooks are kept: SpecTest only adds or removes its own marked block.
"""
import os
import shutil
import stat
import subprocess
from pathlib import Path

BEGIN, END = "# >>> SpecTest {rel} >>>", "# <<< SpecTest {rel} <<<"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def hook_path(root: Path) -> tuple[Path, str]:
    """(the post-commit hook file, this project's folder relative to the repo top). Raises if not a git repo."""
    try:
        top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
        hooks = Path(_git(root, "rev-parse", "--git-path", "hooks"))  # honors core.hooksPath (Husky etc.)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise ValueError(f"{root} is not inside a git repository; run `git init` first.")
    hooks = hooks if hooks.is_absolute() else (root / hooks).resolve()
    return hooks / "post-commit", root.resolve().relative_to(top).as_posix() or "."


def _block(rel: str, workspace: str) -> str:
    exe = shutil.which("spectest")
    exe = Path(exe).as_posix() if exe else "spectest"
    log = f"{workspace}/logs/hook.log"
    return "\n".join([
        BEGIN.format(rel=rel),
        "# Tests each commit with SpecTest in the background; output goes to the log below.",
        f'( cd "$(git rev-parse --show-toplevel)/{rel}" && mkdir -p "{workspace}/logs" && '
        f'nohup "{exe}" run >> "{log}" 2>&1 & )',
        END.format(rel=rel),
    ]) + "\n"


def _strip_block(text: str, rel: str) -> str:
    begin, end = BEGIN.format(rel=rel), END.format(rel=rel)
    out, inside = [], False
    for line in text.splitlines(keepends=True):
        if line.strip() == begin:
            inside = True
        elif line.strip() == end:
            inside = False
        elif not inside:
            out.append(line)
    return "".join(out)


def install_hook(root: Path, workspace_name: str = ".spectest") -> Path:
    """Add (or refresh) this project's block in the post-commit hook. Returns the hook path."""
    path, rel = hook_path(root)
    text = path.read_text(encoding="utf-8") if path.exists() else "#!/bin/sh\n"
    text = _strip_block(text, rel)  # refresh rather than duplicate
    if not text.endswith("\n"):
        text += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + _block(rel, workspace_name), encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)  # git needs it executable
    return path


def remove_hook(root: Path) -> Path | None:
    """Remove this project's block; delete the hook file if nothing else is left. Returns the hook if changed."""
    try:
        path, rel = hook_path(root)
    except ValueError:
        return None
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    stripped = _strip_block(text, rel)
    if stripped == text:
        return None
    if stripped.strip() in ("", "#!/bin/sh"):
        os.remove(path)
    else:
        path.write_text(stripped, encoding="utf-8", newline="\n")
    return path


def has_hook(root: Path) -> bool:
    try:
        path, rel = hook_path(root)
    except ValueError:
        return False
    return path.exists() and BEGIN.format(rel=rel) in path.read_text(encoding="utf-8")
