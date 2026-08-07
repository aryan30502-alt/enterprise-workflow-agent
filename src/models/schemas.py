"""
Pydantic schemas and typed Enums defining the system's exact I/O contracts.

Design constraints:
- All DTOs are frozen (immutable after construction).
- Enums replace every magic string.
- Every Output model implements artifact_updates() — the executor never
  inspects concrete tool names or attribute names to update AgentState.
  This keeps the executor future-proof for Tool #5, Tool #10, etc.
- AgentState uses LangGraph-compatible Annotated reducers for list fields.
- Fully JSON-serializable throughout.
"""

import operator
from enum import Enum
from typing import Annotated, Any, Dict, Generic, List, Optional, TypedDict, TypeVar

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────


class ToolStatus(str, Enum):
    """Execution status for a single tool run."""

    SUCCESS = "success"
    FAILED = "failed"
    RETRIED = "retried"
    SKIPPED = "skipped"


class AgentStatus(str, Enum):
    """Overall state of the agent execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Role(str, Enum):
    """Message roles for conversation history."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# ── Conversation Models ───────────────────────────────────────────────────────


class Message(BaseModel):
    """
    A strict, immutable message structure for conversation history.
    Prevents untyped dicts from leaking into the planner prompt context.
    """

    model_config = {"frozen": True}

    role: Role = Field(..., description="The author of the message.")
    content: str = Field(..., description="The text content of the message.")


# ── ToolOutput base — the artifact_updates() contract ─────────────────────────


class ToolOutput(BaseModel):
    """
    Base class for ALL tool output models.

    Defines the artifact_updates() contract so the executor can generically
    merge tool results into AgentState without ever inspecting tool names or
    concrete attribute names.

    Rule: Every concrete Output model MUST override artifact_updates() and
    return only the AgentState keys it is responsible for updating.
    Adding Tool #5 or #10 requires zero changes to the executor.
    """

    model_config = {"frozen": True}

    def artifact_updates(self) -> Dict[str, Any]:
        """
        Return a partial AgentState update dict for the keys this output owns.

        The executor calls this method on every successful ToolResult and
        merges the returned dict directly into the state update:

            if result.success and result.data:
                updates.update(result.data.artifact_updates())

        Returns:
            Dict[str, Any]: Keys must match AgentState field names exactly.
        """
        return {}


# TypeVar bound to ToolOutput for generic ToolResult and BaseTool typing.
T = TypeVar("T", bound=ToolOutput)


# ── Generic Tool Result ───────────────────────────────────────────────────────


class ToolResult(BaseModel, Generic[T]):
    """
    Standardised result wrapper returned by EVERY tool execute() call.

    Guarantees the executor always receives a consistent envelope regardless
    of whether the tool succeeded or failed. Parametrised by T (a specific
    ToolOutput subclass) for compile-time typing.
    """

    model_config = {"frozen": True}

    tool_name: str = Field(..., description="Name of the tool that executed.")
    success: bool = Field(
        ..., description="True if the tool completed without errors."
    )
    data: Optional[T] = Field(
        None, description="Typed output payload (set when success is True)."
    )
    error: Optional[str] = Field(
        None, description="Error message (set when success is False)."
    )
    duration_seconds: float = Field(
        0.0, description="Execution time in seconds."
    )


# ── Reporting Models ──────────────────────────────────────────────────────────


class StepReport(BaseModel):
    """Represents a single completed step in the final execution report."""

    model_config = {"frozen": True}

    step_number: int = Field(..., description="Sequential step index (1-based).")
    tool_name: str = Field(..., description="Name of the tool executed.")
    status: ToolStatus = Field(..., description="Final execution status.")
    duration_seconds: float = Field(..., description="Wall-clock execution time.")
    retry_count: int = Field(0, description="Agent-level retry count for this tool.")
    output: Optional[str] = Field(
        None, description="Human-readable summary of the tool output."
    )
    error: Optional[str] = Field(
        None, description="Error detail if the step failed permanently."
    )


class ArtifactPaths(BaseModel):
    """Paths and URLs to artifacts generated during a run."""

    model_config = {"frozen": True}

    csv_path: Optional[str] = Field(None, description="Absolute path to the CSV.")
    xlsx_path: Optional[str] = Field(None, description="Absolute path to the XLSX.")
    sheet_url: Optional[str] = Field(None, description="Google Sheet URL.")


class ExecutionReport(BaseModel):
    """Final structured report generated by the reporter node after every run."""

    model_config = {"frozen": True}

    task_id: str = Field(..., description="Unique identifier for this run.")
    prompt: str = Field(..., description="The original user instruction.")
    status: AgentStatus = Field(..., description="Final agent status.")
    total_duration_seconds: float = Field(
        ..., description="Sum of all step durations."
    )
    steps: List[StepReport] = Field(..., description="Ordered step reports.")
    artifacts: ArtifactPaths = Field(..., description="All generated file locations.")


# ── Tool Input Models (frozen, no artifact_updates needed) ────────────────────


class CSVGeneratorInput(BaseModel):
    """Input parameters for the CSV Generator tool."""

    model_config = {"frozen": True}

    num_rows: int = Field(20, description="Number of employee rows to generate.")
    output_dir: str = Field("output", description="Directory to save the CSV file.")


class ExcelInput(BaseModel):
    """Input parameters for the Excel automation tool."""

    model_config = {"frozen": True}

    csv_path: str = Field(..., description="Absolute path to the source CSV to import.")
    output_dir: str = Field("output", description="Directory to save the XLSX workbook.")


class SheetsInput(BaseModel):
    """Input parameters for the Google Sheets upload tool."""

    model_config = {"frozen": True}

    csv_path: str = Field(..., description="Absolute path to the source CSV to upload.")
    title: str = Field(
        "Employee Data - Agent Import",
        description="Worksheet tab title.",
    )


class VerifyInput(BaseModel):
    """Input parameters for the cross-target verification tool."""

    model_config = {"frozen": True}

    csv_path: str = Field(..., description="Absolute path to the source CSV.")
    xlsx_path: str = Field(..., description="Absolute path to the Excel workbook.")
    sheet_id: str = Field(..., description="Google Spreadsheet ID to verify.")


# ── Tool Output Models (each owns its artifact_updates) ───────────────────────


class CSVGeneratorOutput(ToolOutput):
    """Output payload from the CSV Generator tool."""

    csv_path: str = Field(..., description="Absolute path to the saved CSV file.")
    row_count: int = Field(..., description="Data rows written (excluding header).")
    columns: List[str] = Field(..., description="Column headers in the CSV.")

    def artifact_updates(self) -> Dict[str, Any]:
        """Publishes csv_path into AgentState."""
        return {"csv_path": self.csv_path}


class ExcelOutput(ToolOutput):
    """Output payload from the Excel automation tool."""

    xlsx_path: str = Field(..., description="Absolute path to the saved XLSX.")
    sheet_name: str = Field(..., description="Worksheet name where data was written.")
    row_count: int = Field(..., description="Rows written to the Excel file.")

    def artifact_updates(self) -> Dict[str, Any]:
        """Publishes xlsx_path into AgentState."""
        return {"xlsx_path": self.xlsx_path}


class SheetsOutput(ToolOutput):
    """Output payload from the Google Sheets upload tool."""

    spreadsheet_id: str = Field(..., description="ID of the target spreadsheet.")
    spreadsheet_url: str = Field(..., description="Browser URL of the spreadsheet.")
    row_count: int = Field(..., description="Data rows uploaded (excluding header).")

    def artifact_updates(self) -> Dict[str, Any]:
        """Publishes sheet_id into AgentState."""
        return {"sheet_id": self.spreadsheet_id}


class VerifyOutput(ToolOutput):
    """Output payload from the cross-target verification tool."""

    csv_rows: int = Field(..., description="Data row count in the CSV.")
    xlsx_rows: int = Field(..., description="Data row count in the Excel file.")
    sheet_rows: int = Field(..., description="Data row count in the Google Sheet.")
    all_match: bool = Field(..., description="True when all three counts are equal.")
    summary: str = Field(..., description="Human-readable verification result.")

    def artifact_updates(self) -> Dict[str, Any]:
        """
        Publishes verification_passed into AgentState.

        The completion_check_node reads this flag to decide if the workflow
        is done. No node ever checks tool names to determine completion.
        """
        return {"verification_passed": self.all_match}


# ── Agent State (LangGraph TypedDict with reducers) ───────────────────────────


class AgentState(TypedDict):
    """
    The canonical mutable state object passed between all LangGraph nodes.

    List fields use Annotated[List[X], operator.add] reducers so nodes
    return only the NEW items — LangGraph appends them automatically.

    Non-list fields are replaced on each update (standard LangGraph behaviour).
    """

    # Identity
    task_id: str
    original_prompt: str

    # Conversation history — each planner call may append messages
    conversation_history: Annotated[List[Message], operator.add]

    # Planner decision outputs (replaced each cycle)
    next_tool: Optional[str]
    next_tool_args: Optional[Dict[str, Any]]
    planner_reasoning: Optional[str]

    # Artifact paths — updated generically via artifact_updates()
    csv_path: Optional[str]
    xlsx_path: Optional[str]
    sheet_id: Optional[str]
    verification_passed: Optional[bool]

    # Execution metrics — new items appended via reducer
    step_reports: Annotated[List[StepReport], operator.add]
    retry_counts: Dict[str, int]

    # Termination signals — new errors appended via reducer
    status: AgentStatus
    error_log: Annotated[List[str], operator.add]
