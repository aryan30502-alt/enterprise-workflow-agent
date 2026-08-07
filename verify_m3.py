"""
Independent verification script for Milestone 3 — Tools SDK.
Run: python verify_m3.py
"""

import os
import sys

sys.path.insert(0, ".")

# Provide dummy env vars so AppConfig does not fail at import.
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet-id")


def section(title: str) -> None:
    print("\n" + "-" * 60)
    print("  " + title)
    print("-" * 60)


def check(msg: str) -> None:
    print("  [OK] " + msg)


def fail(msg: str) -> None:
    print("  [FAIL] " + msg)
    sys.exit(1)


# -- 1. BaseTool import ---------------------------------------------------------
section("1. BaseTool contract")
from src.tools.base import BaseTool
from src.models.schemas import ToolResult

check("BaseTool imported successfully")

# -- 2. ToolRegistry — all 5 public methods ------------------------------------
section("2. ToolRegistry — 5 public methods")
from src.tools.registry import ToolRegistry
from src.core.exceptions import UnknownToolError

reg = ToolRegistry()
assert reg.list() == [], "list() should return empty list initially"
check("list() -> [] on empty registry")

assert reg.validate_tool_exists("csv_generator") is False
check("validate_tool_exists() -> False for unknown tool")

try:
    reg.get("csv_generator")
    fail("get() should raise UnknownToolError for unknown tool")
except UnknownToolError:
    check("get() -> raises UnknownToolError for unknown tool")

schemas = reg.get_function_schemas()
assert schemas == []
check("get_function_schemas() -> [] on empty registry")

# -- 3. CSVGeneratorTool — independent test ------------------------------------
section("3. CSVGeneratorTool — independent test")
from src.tools.csv_generator.tool import CSVGeneratorTool
from src.models.schemas import CSVGeneratorInput

tool = CSVGeneratorTool()
assert tool.name == "csv_generator"
check(f"name = '{tool.name}'")

# Function schema structure
schema = tool.get_function_schema()
assert schema["name"] == "csv_generator"
assert "description" in schema
assert "parameters" in schema
assert schema["parameters"]["type"] == "object"
assert "properties" in schema["parameters"]
assert "title" not in schema["parameters"], "title must be stripped from parameters"
props = list(schema["parameters"]["properties"].keys())
check(f"get_function_schema() valid — properties: {props}")

# Direct execute() call with typed input
result = tool.execute(CSVGeneratorInput(num_rows=5, output_dir="output/test"))
assert result.success is True, f"execute() failed: {result.error}"
assert result.data.row_count == 5
assert len(result.data.columns) == 7
assert os.path.exists(result.data.csv_path)
csv_path = result.data.csv_path
check(f"execute() -> success, 5 rows, path exists: {csv_path}")

# Agent path: run() with raw dict args
result2 = tool.run({"num_rows": 3, "output_dir": "output/test"})
assert result2.success is True, f"run() failed: {result2.error}"
assert result2.data.row_count == 3
check("run() with valid raw dict -> success, 3 rows")

# Input validation failure path
result_bad = tool.run({"num_rows": "not_an_int"})
assert result_bad.success is False
assert "Input validation failed" in result_bad.error
check("run() with invalid args -> ToolResult(success=False)")

# -- 4. ExcelTool — schema and instantiation only (no COM in CI) ---------------
section("4. ExcelTool — schema and instantiation test")
from src.tools.excel_tool.tool import ExcelTool
from src.models.schemas import ExcelInput

excel_tool = ExcelTool()
assert excel_tool.name == "excel_tool"
check(f"name = '{excel_tool.name}'")

schema = excel_tool.get_function_schema()
assert schema["name"] == "excel_tool"
assert "csv_path" in schema["parameters"]["properties"]
check("get_function_schema() valid — csv_path in properties")

# run() with missing file -> graceful ToolResult failure (no crash)
result_bad_excel = excel_tool.run({"csv_path": "/nonexistent/file.csv", "output_dir": "output/test"})
assert result_bad_excel.success is False
assert result_bad_excel.error is not None
check(f"run() with missing CSV -> graceful failure: {result_bad_excel.error[:60]}...")

# -- 5. SheetsTool — schema and credential path check -------------------------
section("5. SheetsTool — schema and auth path test")
from src.tools.sheets_tool.tool import SheetsTool
from src.models.schemas import SheetsInput

sheets_tool = SheetsTool()
assert sheets_tool.name == "sheets_tool"
check(f"name = '{sheets_tool.name}'")

schema = sheets_tool.get_function_schema()
assert "csv_path" in schema["parameters"]["properties"]
check("get_function_schema() valid — csv_path in properties")

# run() with missing CSV -> graceful failure
result_bad_sheets = sheets_tool.run({"csv_path": "/nonexistent.csv"})
assert result_bad_sheets.success is False
check(f"run() with missing CSV -> graceful failure: {result_bad_sheets.error[:60]}...")

# -- 6. VerifyTool — schema and file path check --------------------------------
section("6. VerifyTool — schema and path test")
from src.tools.verify_tool.tool import VerifyTool
from src.models.schemas import VerifyInput

verify_tool = VerifyTool()
assert verify_tool.name == "verify_tool"
check(f"name = '{verify_tool.name}'")

schema = verify_tool.get_function_schema()
required_props = {"csv_path", "xlsx_path", "sheet_id"}
actual_props = set(schema["parameters"]["properties"].keys())
assert required_props.issubset(actual_props), f"Missing props: {required_props - actual_props}"
check(f"get_function_schema() valid — properties: {sorted(actual_props)}")

# run() with missing CSV -> graceful failure
result_bad_verify = verify_tool.run({
    "csv_path": "/nonexistent.csv",
    "xlsx_path": "/nonexistent.xlsx",
    "sheet_id": "fake-id",
})
assert result_bad_verify.success is False
check(f"run() with missing files -> graceful failure: {result_bad_verify.error[:60]}...")

# -- 7. Global Registry singleton ---------------------------------------------
section("7. Global ToolRegistry singleton")
from src.tools import registry as global_registry

registered = global_registry.list()
for expected in ["csv_generator", "excel_tool", "sheets_tool", "verify_tool"]:
    assert expected in registered, f"'{expected}' not in registry"
check(f"All 4 tools registered: {registered}")

assert len(global_registry) == 4
check("len(registry) == 4")

all_schemas = global_registry.get_function_schemas()
assert len(all_schemas) == 4
for s in all_schemas:
    assert "name" in s
    assert "description" in s
    assert "parameters" in s
    assert "title" not in s["parameters"], f"'title' leaked into {s['name']} parameters"
check("All 4 schemas valid — 'title' not in any parameters block")

# Duplicate registration protection
try:
    from src.tools.csv_generator.tool import CSVGeneratorTool as _CSV
    global_registry.register(_CSV())
    fail("Duplicate registration should raise ValueError")
except ValueError:
    check("Duplicate registration -> ValueError raised correctly")

# validate_tool_exists for all tools
for name in registered:
    assert global_registry.validate_tool_exists(name) is True
assert global_registry.validate_tool_exists("nonexistent_tool") is False
check("validate_tool_exists() correct for all registered and unknown tools")

# -- 8. Registry -> CSV Tool round-trip via registry.get() ---------------------
section("8. Round-trip: registry.get() -> tool.run()")
resolved = global_registry.get("csv_generator")
result = resolved.run({"num_rows": 10, "output_dir": "output/test"})
assert result.success is True, f"Registry round-trip failed: {result.error}"
assert result.data.row_count == 10
check("registry.get('csv_generator').run() -> 10 rows, success=True")

# -- Summary -------------------------------------------------------------------
print()
print("=" * 60)
print("  MILESTONE 3 VERIFICATION: ALL CHECKS PASSED")
print("=" * 60)

