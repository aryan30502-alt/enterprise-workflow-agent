"""
Agent nodes for the LangGraph orchestration layer.

Node contracts:
  - Every node receives AgentState, returns a partial state dict.
  - Nodes NEVER import concrete tool classes.
  - Executor NEVER inspects tool names or output attributes — it calls
    result.data.artifact_updates() generically.
  - Every node stays under ~100 lines; helpers are extracted below.
  - The planner_fn signature is (state, registry) -> dict so both the
    real LLM planner and simulation planners share the same interface.
"""

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.core.config import config
from src.core.exceptions import PlannerError
from src.core.logger import get_logger
from src.models.schemas import (
    AgentState,
    AgentStatus,
    ArtifactPaths,
    ExecutionReport,
    StepReport,
    ToolStatus,
)
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)

# ── Planner decision schema (internal — never exported) ───────────────────────


class PlannerDecision(BaseModel):
    """Structured output the LLM must return on every planning step."""

    reasoning: str = Field(
        ...,
        description=(
            "Think step-by-step about what has been done and what tool is "
            "needed next. Be specific about why."
        ),
    )
    next_tool: str = Field(
        ...,
        description="Exact snake_case name of the tool to execute next.",
    )
    next_tool_args: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Arguments for the selected tool, matching its parameter schema. "
            "Use exact artifact paths from the CURRENT ARTIFACTS section."
        ),
    )


# ── Real LLM planner (Gemini 2.5 Flash) ──────────────────────────────────────


def llm_planner(state: AgentState, registry: ToolRegistry) -> dict:
    """
    Choose the next tool via LLM with structured output.

    Backend priority:
        1. Groq  (fast, free, excellent function calling)
        2. OpenRouter  (free fallback)
        3. Google Generative AI  (requires valid quota)

    Raises:
        PlannerError: If the LLM returns an invalid tool name or fails entirely.
    """
    import time as _time

    if config.groq_api_key:
        from langchain_groq import ChatGroq
        logger.info("planner_llm", backend="groq", model=config.groq_model)
        llm = ChatGroq(
            model=config.groq_model,
            api_key=config.groq_api_key,
            temperature=0,
            timeout=120,
        )
    elif config.openrouter_api_key:
        from langchain_openai import ChatOpenAI
        logger.info("planner_llm", backend="openrouter", model=config.openrouter_model)
        llm = ChatOpenAI(
            model=config.openrouter_model,
            api_key=config.openrouter_api_key,
            base_url=config.openrouter_base_url,
            temperature=0,
            timeout=120,
        )
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        logger.info("planner_llm", backend="google", model=config.gemini_model)
        llm = ChatGoogleGenerativeAI(
            model=config.gemini_model,
            google_api_key=config.google_api_key,
            temperature=0,
            request_timeout=120,
        )

    structured_llm = llm.with_structured_output(PlannerDecision)
    prompt = _build_planner_prompt(state, registry)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            decision: PlannerDecision = structured_llm.invoke(prompt)
            break
        except Exception as exc:
            err_str = str(exc)
            is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate_limit" in err_str.lower()
            if is_rate_limit and attempt < max_retries - 1:
                wait = (attempt + 1) * 20
                logger.warning("llm_rate_limit_retry", attempt=attempt + 1, wait_s=wait)
                _time.sleep(wait)
                continue
            raise PlannerError(f"LLM call failed: {exc!r}") from exc

    if not registry.validate_tool_exists(decision.next_tool):
        raise PlannerError(
            f"LLM hallucinated unknown tool: '{decision.next_tool}'. "
            f"Valid: {registry.list()}"
        )

    return {
        "next_tool": decision.next_tool,
        "next_tool_args": decision.next_tool_args,
        "planner_reasoning": decision.reasoning,
    }


# ── Node factories ────────────────────────────────────────────────────────────


def make_planner_node(
    planner_fn: Callable,
    registry: ToolRegistry,
    panel: Optional[Any] = None,
) -> Callable[[AgentState], dict]:
    """
    Returns a LangGraph-compatible planner node.

    The planner_fn is injectable for simulation (mock planner) or production
    (llm_planner). The node itself stays under 20 lines.
    """

    def planner_node(state: AgentState) -> dict:
        t0 = time.monotonic()
        logger.info("node_start", node="planner", step=len(state["step_reports"]) + 1)

        try:
            updates = planner_fn(state, registry)
        except PlannerError as exc:
            logger.error("planner_error", error=str(exc))
            return {
                "status": AgentStatus.FAILED,
                "error_log": [f"Planner failed: {exc}"],
                "next_tool": None,  # Signal to route_after_planner -> reporter
            }

        if panel:
            panel.update_reasoning(updates.get("planner_reasoning", "")[:200])

        logger.info(
            "node_end",
            node="planner",
            next_tool=updates.get("next_tool"),
            duration=round(time.monotonic() - t0, 3),
        )
        return updates

    return planner_node


def route_after_planner(
    state: AgentState,
) -> Literal["executor", "reporter"]:
    """Route to reporter if planner set status=FAILED; otherwise executor."""
    if state["status"] == AgentStatus.FAILED:
        return "reporter"
    return "executor"


def make_executor_node(
    registry: ToolRegistry,
    panel: Optional[Any] = None,
) -> Callable[[AgentState], dict]:
    """
    Returns a LangGraph-compatible executor node.

    Critically: this node NEVER checks tool_name to decide what state to update.
    It calls result.data.artifact_updates() generically. Any future tool whose
    Output model implements artifact_updates() will work without executor changes.
    """

    def executor_node(state: AgentState) -> dict:
        t0 = time.monotonic()
        tool_name = state.get("next_tool")
        logger.info("node_start", node="executor", tool=tool_name)

        if not tool_name:
            return {
                "status": AgentStatus.FAILED,
                "error_log": ["Executor reached with next_tool=None."],
            }

        tool = registry.get(tool_name)
        result = tool.run(state.get("next_tool_args") or {})

        status = ToolStatus.SUCCESS if result.success else ToolStatus.FAILED
        step = _build_step_report(state, tool_name, result, status)
        updates: Dict[str, Any] = {"step_reports": [step]}

        # Generic artifact merge — zero tool-name inspection.
        if result.success and result.data is not None:
            artifact_delta = result.data.artifact_updates()
            updates.update(artifact_delta)
            if artifact_delta:
                logger.info("artifacts_updated", keys=list(artifact_delta.keys()))

        if panel:
            ui_status = "SUCCESS" if result.success else "FAILED"
            panel.update_step(tool_name, ui_status, f"{result.duration_seconds}s")

        logger.info(
            "node_end",
            node="executor",
            tool=tool_name,
            success=result.success,
            duration=round(time.monotonic() - t0, 3),
        )
        return updates

    return executor_node


def make_reporter_node(
    panel: Optional[Any] = None,
) -> Callable[[AgentState], dict]:
    """Returns a LangGraph-compatible reporter node."""

    def reporter_node(state: AgentState) -> dict:
        t0 = time.monotonic()
        logger.info("node_start", node="reporter", status=state["status"])

        report = _build_execution_report(state)
        _save_report(report)
        _log_report_summary(report)

        if panel:
            panel.stop()

        logger.info(
            "node_end",
            node="reporter",
            duration=round(time.monotonic() - t0, 3),
        )
        return {}  # Terminal node — no state updates needed.

    return reporter_node


# ── Stateless nodes (no closure needed) ──────────────────────────────────────


def error_handler_node(state: AgentState) -> dict:
    """
    Increments retry_counts for the failing tool.
    Sets status=FAILED if max retries are exceeded.
    """
    return make_error_handler_node()(state)


def make_error_handler_node(max_tool_retries: Optional[int] = None) -> Callable[[AgentState], dict]:
    """
    Factory for error_handler_node with injectable max_tool_retries.
    When max_tool_retries is None, falls back to config.max_tool_retries.
    """
    def _error_handler_node(state: AgentState) -> dict:
        t0 = time.monotonic()
        tool_name = state.get("next_tool", "unknown")
        ceiling = max_tool_retries if max_tool_retries is not None else config.max_tool_retries
        logger.info("node_start", node="error_handler", tool=tool_name)

        retry_counts = dict(state["retry_counts"])
        retry_counts[tool_name] = retry_counts.get(tool_name, 0) + 1
        attempt = retry_counts[tool_name]
        msg = f"Tool '{tool_name}' failed (attempt {attempt}/{ceiling})."

        updates: Dict[str, Any] = {
            "retry_counts": retry_counts,
            "error_log": [msg],
        }

        if attempt >= ceiling:
            updates["status"] = AgentStatus.FAILED
            logger.warning("max_retries_exceeded", tool=tool_name, attempts=attempt)

        logger.info("node_end", node="error_handler", duration=round(time.monotonic() - t0, 3))
        return updates

    return _error_handler_node


def completion_check_node(state: AgentState) -> dict:
    """
    Determines whether the agent should continue, finish (COMPLETED),
    or abort (FAILED due to max steps).
    """
    return make_completion_check_node()(state)


def make_completion_check_node(max_agent_steps: Optional[int] = None) -> Callable[[AgentState], dict]:
    """
    Factory for completion_check_node with injectable max_agent_steps.
    When max_agent_steps is None, falls back to config.max_agent_steps.
    """
    def _completion_check_node(state: AgentState) -> dict:
        t0 = time.monotonic()
        step_count = len(state["step_reports"])
        ceiling = max_agent_steps if max_agent_steps is not None else config.max_agent_steps
        logger.info("node_start", node="completion_check", steps=step_count)

        if state.get("verification_passed") is True:
            logger.info("task_complete", steps=step_count)
            return {"status": AgentStatus.COMPLETED}

        if step_count >= ceiling:
            msg = f"Max agent steps reached ({step_count}/{ceiling})."
            logger.warning("max_steps_reached", steps=step_count)
            return {"status": AgentStatus.FAILED, "error_log": [msg]}

        logger.info(
            "node_end",
            node="completion_check",
            verdict="continue",
            duration=round(time.monotonic() - t0, 3),
        )
        return {}

    return _completion_check_node


# ── Routing functions ─────────────────────────────────────────────────────────


def route_after_executor(
    state: AgentState,
) -> Literal["completion_check", "error_handler"]:
    """Error_handler if the last step failed; completion_check otherwise."""
    if state["step_reports"] and state["step_reports"][-1].status == ToolStatus.FAILED:
        return "error_handler"
    return "completion_check"


def route_after_completion_check(
    state: AgentState,
) -> Literal["planner", "reporter"]:
    """Reporter if COMPLETED or FAILED; planner to continue the loop."""
    if state["status"] in (AgentStatus.COMPLETED, AgentStatus.FAILED):
        return "reporter"
    return "planner"


def route_after_error_handler(
    state: AgentState,
) -> Literal["planner", "reporter"]:
    """Reporter if max retries exceeded (FAILED); planner to retry."""
    if state["status"] == AgentStatus.FAILED:
        return "reporter"
    return "planner"


# ── Private helpers (keep nodes thin) ─────────────────────────────────────────


def _build_planner_prompt(state: AgentState, registry: ToolRegistry) -> str:
    """Construct the full planner prompt from current state and registry."""
    tool_schemas = registry.get_function_schemas()

    step_lines = [
        f"  Step {s.step_number}: [{s.status.value.upper()}] {s.tool_name}"
        + (f" — {s.output[:80]}" if s.output else "")
        + (f" | ERROR: {s.error}" if s.error else "")
        for s in state["step_reports"]
    ]

    error_lines = [f"  - {e}" for e in state["error_log"]] or ["  None"]

    return (
        f"OBJECTIVE:\n  {state['original_prompt']}\n\n"
        f"AVAILABLE TOOLS:\n"
        + "\n".join(f"  - {s['name']}: {s['description'][:120]}" for s in tool_schemas)
        + f"\n\nFULL TOOL SCHEMAS (JSON):\n{json.dumps(tool_schemas, indent=2)}\n\n"
        f"CURRENT ARTIFACTS (use these as arguments for downstream tools):\n"
        f"  csv_path:  {state.get('csv_path') or 'NOT YET GENERATED'}\n"
        f"  xlsx_path: {state.get('xlsx_path') or 'NOT YET GENERATED'}\n"
        f"  sheet_id:  {state.get('sheet_id') or 'NOT YET UPLOADED'}\n\n"
        f"COMPLETED STEPS:\n"
        + ("\n".join(step_lines) if step_lines else "  None yet")
        + f"\n\nERRORS:\n"
        + "\n".join(error_lines)
        + "\n\nINSTRUCTION: Select the next tool. Required order: "
        "csv_generator -> excel_tool -> sheets_tool -> verify_tool. "
        "Pass exact artifact paths from CURRENT ARTIFACTS as tool arguments."
    )


def _build_step_report(
    state: AgentState,
    tool_name: str,
    result: Any,
    status: ToolStatus,
) -> StepReport:
    """Construct a StepReport from a ToolResult."""
    return StepReport(
        step_number=len(state["step_reports"]) + 1,
        tool_name=tool_name,
        status=status,
        duration_seconds=result.duration_seconds,
        retry_count=state["retry_counts"].get(tool_name, 0),
        output=str(result.data) if result.data else None,
        error=result.error,
    )


def _build_execution_report(state: AgentState) -> ExecutionReport:
    """Construct the final ExecutionReport from terminal AgentState."""
    sheet_id = state.get("sheet_id")
    return ExecutionReport(
        task_id=state["task_id"],
        prompt=state["original_prompt"],
        status=state["status"],
        total_duration_seconds=round(
            sum(s.duration_seconds for s in state["step_reports"]), 3
        ),
        steps=list(state["step_reports"]),
        artifacts=ArtifactPaths(
            csv_path=state.get("csv_path"),
            xlsx_path=state.get("xlsx_path"),
            sheet_url=(
                f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
                if sheet_id
                else None
            ),
        ),
    )


def _save_report(report: ExecutionReport) -> None:
    """Persist the ExecutionReport as a JSON file in the output directory."""
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{report.task_id}_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report.model_dump_json(indent=2))
    logger.info("report_saved", path=str(report_path), status=report.status.value)


def _log_report_summary(report: ExecutionReport) -> None:
    """Emit a structured summary log line for the completed run."""
    logger.info(
        "execution_complete",
        task_id=report.task_id,
        status=report.status.value,
        total_steps=len(report.steps),
        duration_s=report.total_duration_seconds,
        csv=report.artifacts.csv_path,
        xlsx=report.artifacts.xlsx_path,
        sheet=report.artifacts.sheet_url,
    )
