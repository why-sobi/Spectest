# SpecTest: IncidentZero

SpecTest reads this file at the start of every run. It is this project's own configuration;
other projects have their own SPECTEST.md and their own memory in their own `.spectest/` folder.

## Settings
<!-- `key: value` lines. Paths are relative to this folder and must stay inside it. -->
project_id: incidentzero             # name used in reports and the generated test file name
spec_path: docs/FEATURE_SPEC.md      # natural-language requirements that tests are generated from
source_dir: incidentzero             # code under test (imported by the generated tests)
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
- **For writing tests:** public functions, classes and methods in `incidentzero`: signatures and docstrings only,
  never their bodies, so tests follow the spec, not the code. Skips hidden folders, virtualenvs, `tests/`, and anything in `exclude`.
- **For investigating failures:** the investigator agent may read any project file (sent to the LLM provider),
  except `.env`, keys, databases, `.git/`, `.spectest/` and virtualenvs.
- **Memory:** the previous test suite and lessons from past repairs are used when the spec changes.
- **This file:** settings and test instructions

Detected when `spectest init` ran:
```
# module: incidentzero.agent.controller
class AgentController:
    def __init__(self, model: ModelClient, tools: ToolRegistry, approval: ApprovalGateway, budget: BudgetManager, trace: TraceRecorder) -> None:
    def run(self) -> AgentOutcome:

# module: incidentzero.agent.planner
class Planner:
    def __init__(self, model: ModelClient) -> None:
    def create(self, incident_observation: dict[str, Any], context: list[dict[str, Any]] | None=None) -> AgentPlan:
    def revise(self, current: AgentPlan, trigger: dict[str, Any], state_summary: str) -> AgentPlan:

# module: incidentzero.agent.policies
class RiskPolicy:
    def __init__(self, config_path: str | Path='configs/risk_policy.json') -> None:
    def risk(self, tool_name: str) -> RiskLevel:
    def requires_human_approval(self, tool_name: str) -> bool:
class ReplanPolicy:
    def evaluate(self, tool_result: dict[str, Any]) -> str:
    def should_replan(self, tool_result: dict[str, Any]) -> bool:
class LoopGuard:
    def __init__(self, max_same_action_repeats: int=2) -> None:
    def record(self, action_name: str, arguments: dict[str, Any], current_world_version: int | None=None) -> bool:

# module: incidentzero.agent.prompts

# module: incidentzero.agent.recovery
class RetryPolicy:
    def __init__(self, max_attempts: int=3, sleeper: Callable[[float], None]=time.sleep) -> None:
    def call_model(self, fn: Callable[[], T]) -> T:

# module: incidentzero.agent.state
@dataclass
class AgentState:
    messages: list[dict[str, Any]] = field(default_factory=list)
    plan: AgentPlan | None = None
    evidence_ids: list[str] = field(default_factory=list)
    latest_world_version: int | None = None
    last_tool_results: list[dict[str, Any]] = field(default_factory=list)
    repeated_actions: dict[str, int] = field(default_factory=dict)
    status: str = 'running'
    def observe_result(self, result: dict[str, Any]) -> None:

# module: incidentzero.agent.status

# module: incidentzero.approval.gateway
class ApprovalGateway(Protocol):
    def approve(self, action_name: str, arguments: dict[str, Any], justification: str) -> bool:
class ConsoleApprovalGateway:
    def approve(self, action_name: str, arguments: dict[str, Any], justification: str) -> bool:
class AlwaysApproveGateway:
    def approve(self, action_name: str, arguments: dict[str, Any], justification: str) -> bool:
class AlwaysDenyGateway:
    def approve(self, action_name: str, arguments: dict[str, Any], justification: str) -> bool:

# module: incidentzero.cli
def build_parser() -> argparse.ArgumentParser:
def main() -> None:

# module: incidentzero.domain.models
class RiskLevel(str, Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'
@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
@dataclass(slots=True)
class ModelReply:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
@dataclass(slots=True)
class PlanStep:
    step_id: str
    objective: str
    success_signal: str
    status: str = 'pending'
@dataclass(slots=True)
class AgentPlan:
    hypothesis: str
    steps: list[PlanStep]
    revision: int = 0
    rationale_summary: str = ''
@dataclass(slots=True)
class AgentOutcome:
    status: str
    summary: str
    llm_calls: int
    tool_calls: int
    final_world_version: int | None
    evidence_ids: list[str] = field(default_factory=list)
    trace_path: str | None = None

# module: incidentzero.environment.engine
class SimulationEnvironment:
    def __init__(self, student_id: str, scenario_id: str='public-a') -> None:
    @property
    def world_version(self) -> int:
    @property
    def incident_id(self) -> str:
    def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:

# module: incidentzero.environment.models
@dataclass
class ServiceState:
    name: str
    healthy: bool = True
    replicas: int = 2
    version: str = '1.0.0'
    previous_version: str = '0.9.9'
    error_rate: float = 0.005
    p95_ms: int = 180
    cpu_pct: float = 35.0
    memory_pct: float = 42.0
    cache_hit_rate: float | None = None
    db_connections_pct: float | None = None
    logs: list[str] = field(default_factory=list)
@dataclass
class IncidentSpec:
    incident_id: str
    title: str
    customer_impact: str
    severity: str
    suspected_service: str
    misleading_hint: str
    family: str
    target_service: str
    created_at: str = '2026-09-11T09:00:00Z'
    failure_plan: dict[str, int] = field(default_factory=dict)
    event_at_tool_call: int | None = None
    event_type: str | None = None
    impossible: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)

# module: incidentzero.environment.scenario_factory
def stable_seed(student_id: str, scenario_id: str) -> int:
def build_scenario(student_id: str, scenario_id: str='public-a') -> tuple[IncidentSpec, dict[str, ServiceState], int]:

# module: incidentzero.environment.topology
def upstream_of(target: str) -> list[str]:

# module: incidentzero.model.base
class ModelClient(Protocol):
    def decide(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelReply:
    def structured(self, messages: list[dict[str, Any]], schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:

# module: incidentzero.model.errors
class ModelError(RuntimeError):
class TransientModelError(ModelError):
class PermanentModelError(ModelError):

# module: incidentzero.model.groq_client
class GroqModelClient:
    def __init__(self, api_key: str | None=None, model: str='openai/gpt-oss-20b') -> None:
    def decide(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelReply:
    def structured(self, messages: list[dict[str, Any]], schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:

# module: incidentzero.model.scripted
class ScriptedModelClient:
    def __init__(self, decisions: list[ModelReply] | None=None, structured_outputs: list[dict] | None=None) -> None:
    def decide(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelReply:
    def structured(self, messages: list[dict[str, Any]], schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:

# module: incidentzero.telemetry.budget
class BudgetExceeded(RuntimeError):
@dataclass
class BudgetManager:
    max_llm_calls: int = 14
    max_tool_calls: int = 28
    llm_calls: int = 0
    tool_calls: int = 0
    def consume_llm(self) -> None:
    def consume_tool(self) -> None:
    @property
    def remaining_llm(self) -> int:
    @property
    def remaining_tools(self) -> int:

# module: incidentzero.telemetry.trace
class TraceRecorder:
    def __init__(self, path: str | Path) -> None:
    def record(self, event: str, payload: dict[str, Any]) -> None:

# module: incidentzero.tools.definitions

# module: incidentzero.tools.registry
class ToolRegistry:
    def __init__(self, environment: SimulationEnvironment) -> None:
    @property
    def groq_tools(self) -> list[dict[str, Any]]:
    def validate(self, name: str, arguments: dict[str, Any]) -> tuple[bool, str | None]:
    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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
