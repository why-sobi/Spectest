"""Read-only project access for the investigator agent.

Everything here is enforced in code: paths must stay inside the project, and secrets, VCS internals,
SpecTest's own memory, virtualenvs, and binary files are never returned.
"""
import fnmatch
import os
import re
from pathlib import Path

DENY_DIRS = {".git", ".hg", ".svn", ".spectest", ".venv", "venv", "env", "node_modules", "__pycache__",
             "site-packages", ".mypy_cache", ".pytest_cache", ".idea", ".vscode"}
DENY_FILES = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*", "*.db", "*.sqlite*",
              ".netrc", ".pypirc", "*credentials*", "*secret*"]
MAX_FILE_BYTES = 200_000
MAX_READ_LINES = 300
MAX_LIST = 200
MAX_MATCHES = 50


class Denied(Exception):
    pass


def resolve(root: Path, rel: str) -> Path:
    path = (root / (rel or ".")).resolve()
    if not path.is_relative_to(root):
        raise Denied(f"{rel!r} is outside the project")
    parts = path.relative_to(root).parts
    if any(p in DENY_DIRS for p in parts):
        raise Denied(f"{rel!r} is in a protected folder")
    if path.is_file() and any(fnmatch.fnmatch(path.name.lower(), pat) for pat in DENY_FILES):
        raise Denied(f"{rel!r} may contain secrets")
    return path


def _allowed_file(root: Path, path: Path) -> bool:
    try:
        resolve(root, str(path.relative_to(root)))
        return path.stat().st_size <= MAX_FILE_BYTES
    except (Denied, OSError):
        return False


def _walk(root: Path, start: Path):
    for folder, dirs, names in os.walk(start):
        dirs[:] = sorted(d for d in dirs if d not in DENY_DIRS)
        for n in sorted(names):
            p = Path(folder) / n
            if _allowed_file(root, p):
                yield p


def list_files(root: Path, path: str = ".") -> str:
    start = resolve(root, path)
    if not start.is_dir():
        raise Denied(f"{path!r} is not a folder")
    files = [p.relative_to(root).as_posix() for p in _walk(root, start)]
    more = f"\n... and {len(files) - MAX_LIST} more" if len(files) > MAX_LIST else ""
    return "\n".join(files[:MAX_LIST]) + more or "(empty)"


def read_file(root: Path, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    p = resolve(root, path)
    if not p.is_file():
        raise Denied(f"{path!r} is not a file")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise Denied(f"{path!r} is too large")
    data = p.read_bytes()
    if b"\0" in data[:4096]:
        raise Denied(f"{path!r} is a binary file")
    lines = data.decode("utf-8", errors="replace").splitlines()
    start = max(1, int(start_line or 1))
    end = min(len(lines), int(end_line) if end_line else start + MAX_READ_LINES - 1, start + MAX_READ_LINES - 1)
    body = "\n".join(f"{i:>5}| {lines[i - 1]}" for i in range(start, end + 1))
    tail = f"\n... ({len(lines) - end} more lines; read with start_line={end + 1})" if end < len(lines) else ""
    return f"{p.relative_to(root).as_posix()} (lines {start}-{end} of {len(lines)})\n{body}{tail}"


def search(root: Path, pattern: str, glob: str = "*.py") -> str:
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise Denied(f"invalid regex: {e}")
    hits = []
    for p in _walk(root, root):
        if not fnmatch.fnmatch(p.name, glob):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{p.relative_to(root).as_posix()}:{i}: {line.strip()[:200]}")
                if len(hits) >= MAX_MATCHES:
                    return "\n".join(hits) + "\n... (more matches truncated)"
    return "\n".join(hits) or "(no matches)"
