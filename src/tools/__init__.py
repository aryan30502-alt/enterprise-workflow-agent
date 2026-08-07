"""
src/tools/__init__.py — THE ONLY place where concrete tools are registered.

This module:
1. Instantiates the global ToolRegistry singleton.
2. Registers all concrete tools.
3. Exports ONLY the registry.

Planner and executor nodes do:
    from src.tools import registry

They NEVER import CSVGeneratorTool, ExcelTool, SheetsTool, or VerifyTool
directly. The concrete tool classes are entirely internal to this package.

To add a new tool in the future:
    1. Create src/tools/your_tool/tool.py implementing BaseTool.
    2. Import the class here and call registry.register(YourTool()).
    3. Nothing else needs to change.
"""

from src.tools.csv_generator.tool import CSVGeneratorTool
from src.tools.excel_tool.tool import ExcelTool
from src.tools.registry import ToolRegistry
from src.tools.sheets_tool.tool import SheetsTool
from src.tools.verify_tool.tool import VerifyTool

# ── Global Singleton Registry ─────────────────────────────────────────────────

registry = ToolRegistry()

registry.register(CSVGeneratorTool())
registry.register(ExcelTool())
registry.register(SheetsTool())
registry.register(VerifyTool())

# ── Exports ───────────────────────────────────────────────────────────────────

__all__ = ["registry"]
