"""
src/core/__init__.py
Exposes the core module's public API cleanly.
"""

from src.core.config import AppConfig, config
from src.core.exceptions import (
    BaseAgentError,
    CSVGenerationError,
    ExcelAutomationError,
    GoogleSheetsAPIError,
    MaxRetriesExceededError,
    PlannerError,
    ToolExecutionError,
    UnknownToolError,
    VerificationError,
)
from src.core.logger import (
    AgentProgressPanel,
    get_logger,
    get_rich_console,
    setup_logging,
)

__all__ = [
    # Config
    "AppConfig",
    "config",
    # Exceptions
    "BaseAgentError",
    "ToolExecutionError",
    "CSVGenerationError",
    "ExcelAutomationError",
    "GoogleSheetsAPIError",
    "VerificationError",
    "PlannerError",
    "UnknownToolError",
    "MaxRetriesExceededError",
    # Logging
    "setup_logging",
    "get_logger",
    "get_rich_console",
    "AgentProgressPanel",
]
