"""
LangGraph StateGraph construction for the autonomous agent.

build_graph() is the sole public factory. It accepts optional injectable
dependencies so the graph can be driven by simulation planners and mock
registries during testing, then switched to real implementations for
production with zero code changes.

Dependency injection points:
  planner_fn   - defaults to llm_planner (real Gemini call)
  tool_registry - defaults to the global registry singleton
  panel         - defaults to None (Rich UI panel, optional)
"""

import uuid
from typing import Any, Callable, Optional

from langgraph.graph import END, START, StateGraph

from src.agent.nodes import (
    completion_check_node,
    error_handler_node,
    llm_planner,
    make_completion_check_node,
    make_error_handler_node,
    make_executor_node,
    make_planner_node,
    make_reporter_node,
    route_after_completion_check,
    route_after_error_handler,
    route_after_executor,
    route_after_planner,
)
from src.models.schemas import AgentState, AgentStatus


def build_graph(
    planner_fn: Optional[Callable] = None,
    tool_registry: Optional[Any] = None,
    panel: Optional[Any] = None,
    max_agent_steps: Optional[int] = None,
    max_tool_retries: Optional[int] = None,
):
    """
    Compile and return the autonomous agent StateGraph.

    Graph topology:
        START
          |
        planner  ──────────────────────────────────────┐
          |                                             |
        executor                                        |
          |                                             |
          ├── (success) ──> completion_check            |
          |                     |                       |
          |              (done) ├──> reporter ──> END   |
          |             (cont.) └──────────────────────>┘
          |
          └── (failure) ──> error_handler
                                |
                   (retry) ──>──┘  (via planner)
                   (FAILED) ──> reporter ──> END

    Args:
        planner_fn:      Optional planner callable (state, registry) -> dict.
                         Defaults to llm_planner (real Gemini 2.5 Flash call).
        tool_registry:   Optional ToolRegistry instance.
                         Defaults to the global production registry.
        panel:           Optional AgentProgressPanel for Rich live UI.
                         Pass None in simulations and CI.
        max_agent_steps: Override config.max_agent_steps for this graph instance.
                         Useful in simulation tests without config patching.
        max_tool_retries: Override config.max_tool_retries for this graph instance.

    Returns:
        A compiled LangGraph CompiledStateGraph ready for .invoke().
    """
    # Resolve defaults lazily to avoid circular imports at module level.
    if tool_registry is None:
        from src.tools import registry as default_registry
        tool_registry = default_registry

    resolved_planner = planner_fn if planner_fn is not None else llm_planner

    # Build injectable node functions that respect per-graph overrides.
    from src.agent.nodes import (
        make_completion_check_node,
        make_error_handler_node,
    )
    _completion_check = make_completion_check_node(
        max_agent_steps=max_agent_steps,
    )
    _error_handler = make_error_handler_node(
        max_tool_retries=max_tool_retries,
    )

    workflow = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    workflow.add_node(
        "planner",
        make_planner_node(resolved_planner, tool_registry, panel),
    )
    workflow.add_node(
        "executor",
        make_executor_node(tool_registry, panel),
    )
    workflow.add_node("error_handler", _error_handler)
    workflow.add_node("completion_check", _completion_check)
    workflow.add_node("reporter", make_reporter_node(panel))

    # ── Deterministic edges ───────────────────────────────────────────────────
    workflow.add_edge(START, "planner")
    # NOTE: planner -> executor is CONDITIONAL:
    # If planner fails (status=FAILED), route directly to reporter.
    workflow.add_edge("reporter", END)          # Reporter is the terminal node.

    # ── Conditional edges ─────────────────────────────────────────────────────
    workflow.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "executor": "executor",
            "reporter": "reporter",
        },
    )
    workflow.add_conditional_edges(
        "executor",
        route_after_executor,
        {
            "completion_check": "completion_check",
            "error_handler": "error_handler",
        },
    )
    workflow.add_conditional_edges(
        "completion_check",
        route_after_completion_check,
        {
            "planner": "planner",
            "reporter": "reporter",
        },
    )
    workflow.add_conditional_edges(
        "error_handler",
        route_after_error_handler,
        {
            "planner": "planner",
            "reporter": "reporter",
        },
    )

    return workflow.compile()


def create_initial_state(
    prompt: str,
    task_id: Optional[str] = None,
) -> AgentState:
    """
    Build a well-typed initial AgentState for a new agent run.

    Args:
        prompt:  The natural-language instruction for the agent.
        task_id: Optional ID override. Defaults to a short UUID hex.

    Returns:
        AgentState: A fully-initialised state dict ready for graph.invoke().
    """
    return AgentState(
        task_id=task_id or uuid.uuid4().hex[:8],
        original_prompt=prompt,
        conversation_history=[],
        next_tool=None,
        next_tool_args=None,
        planner_reasoning=None,
        csv_path=None,
        xlsx_path=None,
        sheet_id=None,
        verification_passed=None,
        step_reports=[],
        retry_counts={},
        status=AgentStatus.RUNNING,
        error_log=[],
    )
