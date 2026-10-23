"""Reads the spec and source files; computes hashes, signatures, and the commit SHA."""
import ast
import copy
import hashlib
import os
import subprocess
from pathlib import Path

SKIP_DIRS = {"venv", "env", "__pycache__", "tests", "test", "build", "dist", "node_modules", "site-packages"}
MAX_SIGNATURE_CHARS = 30_000  # keep the LLM prompt bounded on large projects


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_spec(spec_path: Path) -> tuple[str, str]:
    content = read_text(spec_path)
    return content, sha256(content)


def is_skipped(rel_parts: tuple[str, ...], exclude: frozenset[str] = frozenset()) -> bool:
    """True if any folder in a relative path is a skipped/excluded/hidden directory."""
    return any(part in SKIP_DIRS or part in exclude or part.startswith(".") for part in rel_parts)


Dirs = Path | list[Path]  # one source folder or several


def _dirs(source_dirs: Dirs) -> list[Path]:
    return [source_dirs] if isinstance(source_dirs, Path) else list(source_dirs)


def source_files(source_dirs: Dirs, exclude: frozenset[str] = frozenset()) -> list[Path]:
    files = set()  # a set: nested or repeated folders don't list a file twice
    for source_dir in _dirs(source_dirs):
        for folder, dirs, names in os.walk(source_dir):
            dirs[:] = [d for d in dirs if not is_skipped((d,), exclude)]  # prune: never descend into .venv etc.
            files |= {Path(folder) / n for n in names
                      if n.endswith(".py") and n != "__init__.py" and not n.startswith("test_")
                      and n not in ("conftest.py", "setup.py")}
    return sorted(files)


def project_modules(source_dirs: Dirs, root: Path, exclude: frozenset[str] = frozenset()) -> set[str]:
    """Top-level importable names of the project (e.g. {'src'} or {'calculator'})."""
    return {p.relative_to(root).parts[0].removesuffix(".py") for p in source_files(source_dirs, exclude)}


MAX_DOCSTRING_LINES = 12
PUBLIC_DUNDERS = {"__init__", "__call__"}  # constructor/call signatures matter for tests


def _header(node: ast.AST) -> str:
    """`def name(args) -> ret:` / `class Name(Base):` on one line, without decorators or body."""
    stub = copy.copy(node)
    stub.decorator_list, stub.body = [], [ast.Pass()]
    return ast.unparse(stub).split("\n", 1)[0]


def _describe(node: ast.AST, indent: str, docstrings: bool) -> list[str]:
    lines = [f"{indent}@{ast.unparse(d)}" for d in node.decorator_list]
    lines.append(indent + _header(node))
    doc = ast.get_docstring(node) if docstrings else None
    if doc:
        doc_lines = doc.splitlines()
        if len(doc_lines) > MAX_DOCSTRING_LINES:
            doc_lines = doc_lines[:MAX_DOCSTRING_LINES] + ["..."]
        lines += [f'{indent}    """'] + [f"{indent}    {ln}".rstrip() for ln in doc_lines] + [f'{indent}    """']
    if isinstance(node, ast.ClassDef):
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    not child.name.startswith("_") or child.name in PUBLIC_DUNDERS):
                lines += _describe(child, indent + "    ", docstrings)
    return lines


def extract_signatures(source_dirs: Dirs, root: Path, exclude: frozenset[str] = frozenset(),
                       docstrings: bool = True) -> str:
    """Public functions, classes and their methods per module: signatures and docstrings, never bodies.

    Only the interface is sent to the LLM so tests follow the spec, not the implementation.
    """
    lines = []
    for path in source_files(source_dirs, exclude):
        module = ".".join(path.relative_to(root).with_suffix("").parts)
        lines.append(f"# module: {module}")
        try:
            tree = ast.parse(read_text(path))
        except SyntaxError as e:  # still listed; pytest surfaces the error when the tests import it
            lines.append(f"# (could not parse: {e.msg} at line {e.lineno})\n")
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                lines += _describe(node, "", docstrings)
        lines.append("")
    text = "\n".join(lines)
    if len(text) > MAX_SIGNATURE_CHARS:
        text = text[:MAX_SIGNATURE_CHARS] + "\n# ... (truncated; use `exclude` in SPECTEST.md to narrow the scope)"
    return text


def _source_hash(root: Path, source_dirs: Dirs, exclude: frozenset[str]) -> str:
    h = hashlib.sha256()
    for p in source_files(source_dirs, exclude):
        h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def commit_sha(root: Path, source_dirs: Dirs, exclude: frozenset[str] = frozenset()) -> str:
    """Current git HEAD (with a '-dirty' marker for uncommitted source changes).

    Without git, or before the first commit, falls back to a hash of the source files.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", *map(str, _dirs(source_dirs))], cwd=root, capture_output=True, text=True
        ).stdout.strip()
        if dirty:
            return f"{head}-dirty-{_source_hash(root, source_dirs, exclude)[:8]}"
        return head
    except (subprocess.CalledProcessError, FileNotFoundError):
        return f"nogit-{_source_hash(root, source_dirs, exclude)[:12]}"
