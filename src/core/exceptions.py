"""
Custom exception hierarchy for the autonomous agent system.

Rule: Business logic NEVER raises base `Exception` or any built-in exception
directly. All exceptions are sub-classes of `BaseAgentError` so callers can
catch selectively with precision.
"""


class BaseAgentError(Exception):
    """Root of all agent-specific exceptions."""


# ── Tool-level exceptions ─────────────────────────────────────────────────────


class ToolExecutionError(BaseAgentError):
    """
    Raised internally when a concrete tool's logic encounters an unrecoverable
    error. Tool nodes catch this and convert it to a failed ToolResult so the
    agent graph always receives a valid return value.
    """


class CSVGenerationError(ToolExecutionError):
    """Raised when CSV generation fails (e.g., Faker or filesystem error)."""


class ExcelAutomationError(ToolExecutionError):
    """
    Raised when Excel COM automation fails via pywin32.
    Common causes: Excel not installed, file locked, COM dispatch failure.
    """


class GoogleSheetsAPIError(ToolExecutionError):
    """
    Raised when the Google Sheets API call fails after all tenacity retries
    are exhausted. Includes the underlying gspread exception message.
    """


class VerificationError(ToolExecutionError):
    """
    Raised when the VerifyTool cannot read one of the three data sources
    (CSV, XLSX, or Google Sheet) required for row-count comparison.
    """


# ── Agent-level exceptions ────────────────────────────────────────────────────


class PlannerError(BaseAgentError):
    """
    Raised when the LLM returns output that cannot be parsed into a valid
    PlannerDecision (e.g., unknown tool name, missing arguments, malformed JSON).
    """


class UnknownToolError(BaseAgentError):
    """
    Raised by the ToolRouter conditional edge when the Planner selects a tool
    name that is not registered in the ToolRegistry.
    """


class MaxRetriesExceededError(BaseAgentError):
    """
    Raised by the error_node when `retry_counts[tool_name]` reaches or exceeds
    `config.max_tool_retries`. Causes the graph to route to the reporter node.
    """
