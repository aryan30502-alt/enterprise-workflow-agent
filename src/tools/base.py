"""
BaseTool — the abstract contract that every tool in this SDK must satisfy.

Design principles enforced here:
- Generic[InputT, OutputT] provides compile-time type safety per-tool.
- execute() is the ONLY business logic entry point. Subclasses implement it.
- run() is the agent's entry point. It validates raw LLM-provided args via
  Pydantic before delegating to execute(), and catches all uncaught exceptions
  so the agent graph always receives a valid ToolResult (never raises).
- get_function_schema() converts the input Pydantic model to the
  Gemini/OpenAI function-calling JSON format automatically.
- No tool may call another tool. No tool may import from agent/ or planner/.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from src.models.schemas import ToolOutput, ToolResult

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=ToolOutput)


class BaseTool(ABC, Generic[InputT, OutputT]):
    """
    Abstract base class for all agent tools.

    Every concrete tool MUST declare these class variables:
        name          - unique snake_case identifier used by the ToolRegistry
        description   - sent to the LLM in the function schema; be specific
        input_schema  - the Pydantic model class for validated input
        output_schema - the Pydantic model class for typed output

    Dependency direction:
        Planner → Registry → BaseTool → Pydantic Models
    """

    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[Type[BaseModel]]
    output_schema: ClassVar[Type[BaseModel]]

    # Optional metadata — override in subclasses if desired.
    version: ClassVar[str] = "1.0"
    author: ClassVar[str] = "agent_project"

    # ── Public Agent Entry Point ──────────────────────────────────────────────

    def run(self, raw_args: Dict[str, Any]) -> ToolResult:
        """
        Called by the agent executor node. Never call execute() directly from
        outside the tool package.

        Steps:
          1. Validate raw_args against self.input_schema.
          2. If validation fails, return a failed ToolResult immediately.
          3. Delegate to self.execute() with a fully-typed input object.
          4. If execute() raises an unexpected exception, catch it and return
             a failed ToolResult. Never propagate.

        Args:
            raw_args: The dict of kwargs produced by the LLM planner.

        Returns:
            ToolResult: Always. Never raises.
        """
        start = time.monotonic()

        try:
            input_data = self.input_schema.model_validate(raw_args)
        except ValidationError as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Input validation failed: {exc.errors()}",
                duration_seconds=round(time.monotonic() - start, 3),
            )

        try:
            return self.execute(input_data)
        except Exception as exc:  # noqa: BLE001 — last-resort safety net
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Unexpected error in {self.name}: {exc!r}",
                duration_seconds=round(time.monotonic() - start, 3),
            )

    # ── Abstract Contract ─────────────────────────────────────────────────────

    @abstractmethod
    def execute(self, input_data: InputT) -> ToolResult:
        """
        Implement all business logic here.

        Concrete tools MUST:
        - Return ToolResult[OutputT] on success.
        - Return ToolResult with success=False and error message on failure.
        - Track duration internally using time.monotonic().
        - Never raise exceptions to the caller.
        - Never call another tool.

        Args:
            input_data: Fully-validated Pydantic input model.

        Returns:
            ToolResult: Always. Never raises.
        """

    # ── Schema Introspection ──────────────────────────────────────────────────

    def get_function_schema(self) -> Dict[str, Any]:
        """
        Generates the Gemini/OpenAI-compatible function-calling schema.

        Converts the Pydantic input model's JSON Schema into the format
        expected by the LLM's tool/function calling API:

            {
                "name": "tool_name",
                "description": "...",
                "parameters": {
                    "type": "object",
                    "properties": { ... }
                }
            }

        Returns:
            Dict[str, Any]: A single function schema dict.
        """
        raw_schema = self.input_schema.model_json_schema()

        # Strip Pydantic-added top-level keys that are not part of the
        # parameters object sent to the LLM.
        parameters: Dict[str, Any] = {
            k: v
            for k, v in raw_schema.items()
            if k not in ("title", "description")
        }

        return {
            "name": self.name,
            "description": self.description,
            "parameters": parameters,
        }

    def metadata(self) -> Dict[str, Any]:
        """
        Return a structured, fully JSON-serialisable metadata dict for this tool.

        Includes the tool's identity fields and both Pydantic input/output
        models serialised as JSON Schema dicts. Useful for documentation,
        audit logs, and the execution report.

        Returns:
            Dict[str, Any]:
                {
                    "name":          str,
                    "description":   str,
                    "version":       str,
                    "author":        str,
                    "input_schema":  dict  (JSON Schema of the input model),
                    "output_schema": dict  (JSON Schema of the output model),
                }
        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "input_schema": self.input_schema.model_json_schema(),
            "output_schema": self.output_schema.model_json_schema(),
        }

    def __repr__(self) -> str:
        return f"<Tool name={self.name!r}>"
