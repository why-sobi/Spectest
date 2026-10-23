"""Validates generated test code, guards agent repairs, and runs pytest in a subprocess."""
import ast
import os
import re
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# Generated code is untrusted: only these top-level imports are allowed.
ALLOWED_IMPORTS = {"pytest", "math", "decimal", "fractions", "re", "datetime", "base64", "io", "json", "types",
                   "collections", "itertools", "functools", "dataclasses", "typing", "enum", "string"}
IO_FILE_ACCESS = {"open", "open_code", "FileIO"}  # `io` is allowed for BytesIO/StringIO, not for opening files
PYTEST_TIMEOUT = 300  # seconds for the whole suite
SKIP_MARKERS = {"skip", "skipif", "xfail", "importorskip"}
MIN_SPEC_QUOTE = 10  # characters (after normalizing)


def validate_test_code(code: str, project_modules: set[str]) -> str | None:
    """Return an error message if the code is invalid or unsafe, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            if isinstance(node, ast.Name) and node.id in {"eval", "exec", "__import__", "open", "compile"}:
                return f"Disallowed builtin: {node.id}"
            if (isinstance(node, ast.Attribute) and node.attr in IO_FILE_ACCESS
                    and isinstance(node.value, ast.Name) and node.value.id == "io"):  # io.open(...), io.FileIO(...)
                return f"Disallowed file access: io.{node.attr} (use the tmp_path fixture)"
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "io":
            blocked = [a.name for a in node.names if a.name in IO_FILE_ACCESS or a.name == "*"]
            if blocked:
                return f"Disallowed file access: from io import {', '.join(blocked)} (use the tmp_path fixture)"
        for mod in modules:
            top = mod.split(".")[0]
            if top not in ALLOWED_IMPORTS and top not in project_modules:
                return f"Disallowed import: {mod}"

    if not test_functions(tree):
        return "No test_ functions found"
    return None


def test_functions(tree: ast.AST) -> dict[str, str]:
    """name -> normalized AST dump of every test function (module level or inside Test classes)."""
    return {n.name: ast.dump(n) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")}


# Models often "type" typographic characters when quoting: non-breaking hyphens, curly quotes, en dashes...
TYPOGRAPHY = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
                            "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", " ": " "})


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(TYPOGRAPHY)
    return re.sub(r"[\s`*_]+", " ", text).strip().lower()


def quote_in_spec(quote: str, spec: str) -> bool:
    """True if `quote` (10+ characters) appears in the spec, ignoring whitespace, case, Markdown emphasis and
    typographic variants of dashes, quotes and spaces."""
    q = _normalize(quote)
    return len(q) >= MIN_SPEC_QUOTE and q in _normalize(spec)


def check_repair(old_code: str, new_code: str, repaired: list[str], failing: set[str], spec: str,
                 spec_quote: str, project_modules: set[str]) -> str | None:
    """Deterministic rules for an agent-proposed test fix. Returns a rejection reason, or None if allowed.

    The agent may only change tests that are failing right now, may not delete tests or skip them, and must
    quote the spec text that shows the test (not the code) is wrong.
    """
    problem = validate_test_code(new_code, project_modules)
    if problem:
        return problem
    tree = ast.parse(new_code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in SKIP_MARKERS:
            return f"Skipping tests is not allowed (found `{node.attr}`)"

    old, new = test_functions(ast.parse(old_code)), test_functions(tree)
    removed = sorted(set(old) - set(new))
    if removed:
        return f"Deleting or renaming tests is not allowed: {', '.join(removed)}"
    changed = {name for name in old if old[name] != new[name]}
    undeclared = sorted(changed - set(repaired))
    if undeclared:
        return f"Changed tests not listed in repaired_tests: {', '.join(undeclared)}"
    not_failing = sorted(changed - failing)
    if not_failing:
        return f"Only currently failing tests may be changed; these were passing: {', '.join(not_failing)}"
    if not changed:
        return "No existing test was changed"
    if not quote_in_spec(spec_quote, spec):
        return "spec_quote must be an exact passage (10+ characters) from the spec that proves the test is wrong"
    return None


@dataclass
class RunResult:
    exit_code: int
    total: int
    passed: int
    failed: int
    output: str
    failing: list[str] = field(default_factory=list)  # names of failing tests


def run_pytest(tests_dir: Path, root: Path, report_xml: Path, python: str = sys.executable,
               timeout: int = PYTEST_TIMEOUT, select: str | None = None) -> RunResult:
    """Run the suite (or only test functions whose name matches `select`)."""
    report_xml.unlink(missing_ok=True)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(root), os.environ.get("PYTHONPATH")]))}
    cmd = [python, "-m", "pytest", str(tests_dir), "--tb=short", "-q", "-p", "no:cacheprovider",
           # importlib mode: generated test files can't clash with same-named test files in the project
           "--import-mode=importlib", f"--junitxml={report_xml}"]
    if select:
        cmd += ["-k", select]
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return RunResult(-1, 1, 0, 1, f"pytest timed out after {timeout}s (infinite loop or blocking call?)\n"
                                      + partial[-4000:])
    total = failed = 0
    failing = []
    if report_xml.exists():
        suite = ET.parse(report_xml).getroot()
        suite = suite.find("testsuite") if suite.tag == "testsuites" else suite
        total = int(suite.get("tests", 0))
        failed = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        total -= int(suite.get("skipped", 0))
        failing = [case.get("name", "").split("[")[0] for case in suite.iter("testcase")
                   if case.find("failure") is not None or case.find("error") is not None]
    # pytest exit codes: 0 = all passed, 1 = failures; anything else (collection error etc.) counts as failure
    if proc.returncode not in (0, 1) and failed == 0 and not (select and proc.returncode == 5):
        failed = max(total, 1)
        total = max(total, 1)
    return RunResult(proc.returncode, total, total - failed, failed, (proc.stdout + proc.stderr)[-8000:],
                     sorted(set(failing)))
