"""
ToolRegistry — the single source of truth for all available tools.

Rules enforced by this module:
- This is the ONLY place where tools are registered.
- No business logic lives here. The registry is a typed container.
- Planner and executor nodes resolve tools ONLY through this registry.
  They never import concrete tool classes.
- The registry exposes function schemas for the LLM planner.
"""

from typing import Any, Dict, List

from src.core.exceptions import UnknownToolError
from src.core.logger import get_logger
from src.tools.base import BaseTool

logger = get_logger(__name__)


class ToolRegistry:
    """
    A typed container for BaseTool instances.

    Exposes a clean public API for tool resolution, listing, and schema
    generation. Contains zero business logic — it only routes.

    Usage:
        registry = ToolRegistry()
        registry.register(CSVGeneratorTool())
        tool = registry.get("csv_generator")
        result = tool.run({"num_rows": 20})
    """

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool instance.

        Args:
            tool: A fully initialised BaseTool subclass instance.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered. "
                "Call unregister() first to replace it."
            )
        self._tools[tool.name] = tool
        logger.info("tool_registered", tool_name=tool.name)

    def unregister(self, name: str) -> None:
        """
        Remove a previously registered tool.

        Args:
            name: The tool's unique name.

        Raises:
            UnknownToolError: If no tool with that name is registered.
        """
        if name not in self._tools:
            raise UnknownToolError(
                f"Cannot unregister '{name}': tool is not registered."
            )
        del self._tools[name]
        logger.info("tool_unregistered", tool_name=name)

    # ── Resolution ────────────────────────────────────────────────────────────

    def get(self, name: str) -> BaseTool:
        """
        Retrieve a registered tool by name.

        Args:
            name: The tool's unique snake_case name.

        Returns:
            BaseTool: The registered tool instance.

        Raises:
            UnknownToolError: If no tool with that name is registered.
        """
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(self._tools.keys()) or "none"
            raise UnknownToolError(
                f"Tool '{name}' is not registered. "
                f"Available tools: [{available}]"
            )
        return tool

    # ── Inspection ────────────────────────────────────────────────────────────

    def list(self) -> List[str]:
        """
        Return the names of all currently registered tools.

        Returns:
            List[str]: Sorted list of tool names.
        """
        return sorted(self._tools.keys())

    def get_function_schemas(self) -> List[Dict[str, Any]]:
        """
        Generate the complete list of function schemas for ALL registered tools.

        This is called by the Planner node to pass tool definitions to the
        Gemini LLM. The list is regenerated fresh on every call to ensure
        newly registered tools are always included.

        Returns:
            List[Dict[str, Any]]: One schema dict per registered tool,
                in registration order.
        """
        return [tool.get_function_schema() for tool in self._tools.values()]

    def validate_tool_exists(self, name: str) -> bool:
        """
        Check whether a tool name is registered without raising an exception.

        Use this for soft checks (e.g., in the router node before routing).
        Use get() when you intend to call the tool immediately.

        Args:
            name: The tool name to check.

        Returns:
            bool: True if the tool is registered, False otherwise.
        """
        return name in self._tools

    # ── Dunder ───────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        names = ", ".join(self._tools.keys()) or "empty"
        return f"<ToolRegistry tools=[{names}]>"
