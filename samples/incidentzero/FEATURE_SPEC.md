# IncidentZero Feature Specification (controller reliability layer)

IncidentZero is a bounded autonomous incident-response agent. This spec covers its deterministic reliability
components. The simulator and live model calls are out of scope; tests must not call Groq or the network.
Run tests from the project root (configuration files live in `configs/`).

## incidentzero.telemetry.budget.BudgetManager
- Created with `max_llm_calls` and `max_tool_calls` (defaults 14 and 28); both counters start at 0.
- `consume_llm()` increments `llm_calls`. Once `llm_calls` has reached `max_llm_calls`, a further call raises
  `BudgetExceeded` and the counter does not change.
- `consume_tool()` behaves the same way for `tool_calls` / `max_tool_calls`.
- `remaining_llm` and `remaining_tools` return the maximum minus the calls used so far.
- Example: with `max_llm_calls=2`, two `consume_llm()` calls succeed, the third raises `BudgetExceeded`, and
  `remaining_llm` is 0.

## incidentzero.agent.recovery.RetryPolicy
- Created with `max_attempts` (default 3) and a `sleeper` function used for waiting (so tests can pass a fake).
- `call_model(fn)` calls `fn()` and returns its result.
- If `fn` raises `TransientModelError`, it is retried until it succeeds or `max_attempts` attempts have been made;
  after the last failed attempt the `TransientModelError` is raised to the caller.
- Waits between attempts use exponential backoff: 1 second after the first failure, 2 seconds after the second,
  4 after the third, and so on. No wait happens after the final failed attempt.
- `PermanentModelError` (and any other exception) is never retried: it propagates after a single attempt.
- Example: with `max_attempts=3` and a function that always raises `TransientModelError`, the function is called 3
  times, the sleeper is called with 1 and then 2, and the error is raised.

## incidentzero.agent.policies.LoopGuard
- Created with `max_same_action_repeats` (default 2).
- `record(action_name, arguments, current_world_version=None)` returns `True` when the exact same action (same name
  and same arguments) has now been recorded more than `max_same_action_repeats` times, otherwise `False`.
- Arguments are compared by value: the same keys and values in a different order count as the same action.
- Different arguments, or a different action name, are counted separately.
- When `current_world_version` is given and differs from the last one seen, all counts are reset, because the
  world changed and repeating an action may be meaningful again.
- Example: with the default limit, recording `("get_logs", {"service": "api", "limit": 5})` three times returns
  `False`, `False`, `True`.

## incidentzero.agent.policies.ReplanPolicy
- `evaluate(tool_result)` returns `"continue"`, `"retry"` or `"replan"` based on the result's `status` and
  `retryable` fields:
  - `"ok"` -> `"continue"`.
  - `"loop_detected"`, `"approval_denied"`, `"validation_error"` or `"stale_precondition"` -> `"replan"`, even if
    `retryable` is true.
  - any other status with `retryable: true` -> `"retry"`.
  - anything else (e.g. `"error"`, `"failed"`, unknown statuses) -> `"replan"`.
- `should_replan(tool_result)` returns `True` exactly when `evaluate` returns `"replan"`.

## incidentzero.agent.policies.RiskPolicy
- Reads the risk level of each tool from `configs/risk_policy.json` (default path).
- `risk(tool_name)` returns a `RiskLevel`; a tool missing from the file is treated as `RiskLevel.CRITICAL`.
- `requires_human_approval(tool_name)` is `True` for HIGH and CRITICAL tools, `False` for LOW and MEDIUM.
- With the shipped configuration: `get_metrics` is LOW, `restart_service` is MEDIUM (no approval needed),
  `rollback_deployment` is HIGH and `failover_database` is CRITICAL (both need approval).

## incidentzero.tools.registry.ToolRegistry
- Created with a `SimulationEnvironment` (e.g. `SimulationEnvironment("22I-1234")`, which starts at world version 1).
- `validate(name, arguments)` returns `(True, None)` for a known tool with arguments matching its JSON schema.
- For an unknown tool it returns `(False, "Unknown tool: <name>")`.
- For arguments that break the schema (missing required field, wrong type, out-of-range value, extra field) it
  returns `False` and a non-empty error message.
- `execute(name, arguments)` with invalid arguments does not touch the environment and returns a result with
  `status` `"validation_error"`, `retryable` `False`, `evidence_id` `None`, `data` `None`, the current
  `world_version`, and the validation message in `message`.

## incidentzero.agent.state.AgentState
- `observe_result(result)` records a tool result:
  - a non-empty `evidence_id` is appended to `evidence_ids`;
  - an integer `world_version` becomes `latest_world_version` (other values leave it unchanged);
  - the result is appended to `last_tool_results`, which keeps only the 8 most recent results.

## incidentzero.telemetry.trace.TraceRecorder
- `TraceRecorder(path)` creates the parent folders and starts with an empty file at `path`.
- `record(event, payload)` appends one JSON line with the keys `ts` (a Unix timestamp), `event` and `payload`.
