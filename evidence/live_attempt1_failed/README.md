# First live attempt (failed): kept as evidence

Date: 2026-10-27. Target: IncidentZero copy, spec `samples/incidentzero/FEATURE_SPEC.md`.

Test generation was rejected three times in a row by SpecTest's deterministic import check:

| Attempt | Provider | Rejected because |
|---|---|---|
| 1 | Groq `openai/gpt-oss-120b` | `Disallowed import: time` |
| 2 | Groq `openai/gpt-oss-120b` | `Disallowed import: pathlib` |
| 3 | Gemini `gemini-2.5-flash` | `Disallowed import: time` |

SpecTest handled this correctly: nothing was run, no report was sent, and the run ended with a clear error.
The evaluation script then stopped because it expected a generated test file.

**Cause:** the safe-import allow-list was tuned on a toy calculator project and was too strict for real tests,
which reasonably use `time` (timestamps) and `pathlib`.

**Fix:** harmless standard-library modules were added to the allow-list (`time`, `pathlib`, `unittest`, `tempfile`,
`copy`, ...). `os`, `sys`, `subprocess`, `shutil`, `socket`, network modules, `ctypes`, `pickle` and `importlib`
stay blocked. The generator prompt now lists the allowed modules from the same list, so they can't drift apart.
Logs: `agent_log.jsonl`, step outputs `01_C1.txt`, `02_C1.txt`.
