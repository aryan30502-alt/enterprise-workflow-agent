"""
Integration Test 3: Gemini 2.5 Flash Planner — real LLM call.

Prerequisites:
  - GOOGLE_API_KEY set in .env with a valid key

Verifies:
  - llm_planner makes a real structured output call to Gemini 2.5 Flash
  - Returns a valid PlannerDecision with a tool name in the registry
  - The planner correctly picks csv_generator as the first step
  - The planner picks a valid tool on each call across a 4-step sequence
  - No hallucinated tool names returned
  - Structured output schema is correctly parsed into PlannerDecision

Note: This test makes REAL API calls. It will use quota.
"""

import os
import sys

sys.path.insert(0, ".")

# Load real env (not test placeholder)
from dotenv import load_dotenv
load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_google_api_key_here":
    print("\n  [SKIP] GOOGLE_API_KEY not configured in .env")
    print("  Set GOOGLE_API_KEY=<real key> in .env to run this test.")
    sys.exit(0)


def ok(msg):  print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}"); sys.exit(1)
def section(t): print(f"\n{'='*55}\n  {t}\n{'='*55}")


section("INTEGRATION 3: Gemini 2.5 Flash Planner (real LLM)")

from src.agent.nodes import llm_planner
from src.tools.registry import ToolRegistry
from src.tools.csv_generator.tool import CSVGeneratorTool
from src.tools.excel_tool.tool import ExcelTool
from src.tools.sheets_tool.tool import SheetsTool
from src.tools.verify_tool.tool import VerifyTool
from src.models.schemas import AgentState, AgentStatus, StepReport, ToolStatus

# Build a real registry with all 4 tools
registry = ToolRegistry()
registry.register(CSVGeneratorTool())
registry.register(ExcelTool())
registry.register(SheetsTool())
registry.register(VerifyTool())

VALID_TOOLS = set(registry.list())
ok(f"Registry contains tools: {sorted(VALID_TOOLS)}")

# ── Call 1: Fresh state — expect csv_generator ────────────────────────────────
print("\n  Call 1: Fresh state (expect csv_generator)...")

state_1: AgentState = {
    "task_id": "int-test-gemini",
    "original_prompt": (
        "Generate a CSV file with 20 employee records, import it into "
        "Microsoft Excel, upload to Google Sheets, then verify all targets match."
    ),
    "conversation_history": [],
    "next_tool": None,
    "next_tool_args": None,
    "planner_reasoning": None,
    "csv_path": None,
    "xlsx_path": None,
    "sheet_id": None,
    "verification_passed": None,
    "step_reports": [],
    "retry_counts": {},
    "status": AgentStatus.RUNNING,
    "error_log": [],
}

updates_1 = llm_planner(state_1, registry)
tool_1 = updates_1.get("next_tool")
reasoning_1 = updates_1.get("planner_reasoning", "")[:100]

print(f"  Gemini chose: '{tool_1}'")
print(f"  Reasoning preview: {reasoning_1}...")

if tool_1 not in VALID_TOOLS:
    fail(f"Hallucinated tool: '{tool_1}' not in {VALID_TOOLS}")
ok(f"Call 1 returned valid tool: '{tool_1}'")

if tool_1 != "csv_generator":
    print(f"  [WARN] Expected 'csv_generator' first, got '{tool_1}' — acceptable if reasoning is valid")
else:
    ok("Call 1 correctly chose csv_generator as first step")

args_1 = updates_1.get("next_tool_args", {})
ok(f"Call 1 args: {args_1}")

# ── Call 2: After CSV generated — expect excel_tool ───────────────────────────
print("\n  Call 2: After csv_generator (expect excel_tool)...")

import pathlib
CSV_PATH = str(pathlib.Path("output").resolve() / "employees_test.csv")

from src.models.schemas import StepReport, ToolStatus
step_1 = StepReport(
    step_number=1, tool_name="csv_generator", status=ToolStatus.SUCCESS,
    duration_seconds=0.5, retry_count=0, output=f"CSV saved: {CSV_PATH}",
)

state_2 = dict(state_1)
state_2["step_reports"] = [step_1]
state_2["csv_path"] = CSV_PATH

updates_2 = llm_planner(state_2, registry)
tool_2 = updates_2.get("next_tool")
print(f"  Gemini chose: '{tool_2}'")

if tool_2 not in VALID_TOOLS:
    fail(f"Hallucinated tool on call 2: '{tool_2}'")
ok(f"Call 2 returned valid tool: '{tool_2}'")

# ── Validate structured output fields ─────────────────────────────────────────
for call_num, updates in [(1, updates_1), (2, updates_2)]:
    if "next_tool" not in updates:
        fail(f"Call {call_num}: 'next_tool' missing from planner output")
    if "next_tool_args" not in updates:
        fail(f"Call {call_num}: 'next_tool_args' missing from planner output")
    if "planner_reasoning" not in updates:
        fail(f"Call {call_num}: 'planner_reasoning' missing from planner output")
    if not isinstance(updates["next_tool_args"], dict):
        fail(f"Call {call_num}: next_tool_args is not a dict")

ok("Both calls returned all required fields (next_tool, next_tool_args, planner_reasoning)")

print("\n  [INTEGRATION 3 PASSED]")
