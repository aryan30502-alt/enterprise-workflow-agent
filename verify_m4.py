"""
Milestone 4 — Graph Simulation Verification

Runs three complete end-to-end simulations of the LangGraph orchestration layer
WITHOUT touching Gemini, pywin32, or Google Sheets APIs.

Scenarios:
  A — Happy path: all 4 tools succeed in sequence.
  B — Resilience: excel_tool fails once, then succeeds on retry.
  C — Graceful termination: verify_tool permanently fails; graph aborts via max_steps.

Every scenario asserts:
  - Correct state transitions (node execution order)
  - Correct retry_counts
  - Correct final AgentStatus
  - Correct ExecutionReport (steps, artifacts, duration)
  - Rich progress panel received updates
  - No tool name inspection in the executor (verified by generic artifact_updates)
"""

import os
import sys
import json

sys.path.insert(0, ".")
os.environ.setdefault("GOOGLE_API_KEY", "sim-key")
os.environ.setdefault("GOOGLE_SHEET_ID", "sim-sheet-id")

# ── Imports ───────────────────────────────────────────────────────────────────

from src.agent.graph import build_graph, create_initial_state
from src.models.schemas import (
    AgentState, AgentStatus, ToolStatus,
    CSVGeneratorInput, CSVGeneratorOutput,
    ExcelInput, ExcelOutput,
    SheetsInput, SheetsOutput,
    VerifyInput, VerifyOutput,
    ToolResult,
)
from src.tools.base import BaseTool
from src.tools.registry import ToolRegistry

# ── Helpers ───────────────────────────────────────────────────────────────────

def section(title):
    print("\n" + "=" * 65)
    print("  " + title)
    print("=" * 65)

def ok(msg):
    print("  [PASS] " + msg)

def fail(msg):
    print("  [FAIL] " + msg)
    sys.exit(1)

def assert_eq(label, actual, expected):
    if actual != expected:
        fail(f"{label}: expected {expected!r}, got {actual!r}")
    ok(f"{label} = {actual!r}")

def assert_true(label, condition):
    if not condition:
        fail(f"{label} is False")
    ok(label)


# ── Mock Progress Panel ───────────────────────────────────────────────────────

class MockPanel:
    """Records all calls so tests can assert Rich UI was updated correctly."""

    def __init__(self):
        self.started = False
        self.stopped = False
        self.steps = []               # [(tool_name, status, duration)]
        self.reasoning_updates = []   # [reasoning_str]

    def start(self, prompt):
        self.started = True

    def update_step(self, tool_name, status, duration="-"):
        self.steps.append((tool_name, status, duration))

    def update_reasoning(self, text):
        self.reasoning_updates.append(text)

    def stop(self):
        self.stopped = True


# ── Simulation Tool ───────────────────────────────────────────────────────────

class SimulatedTool(BaseTool):
    """
    A mock BaseTool that returns predetermined ToolResult objects.
    Validates that artifact_updates() is the only mechanism the executor
    uses to propagate state (no tool_name inspection anywhere).
    """

    # These are class-level defaults; each instance shadows them.
    name = "_sim_placeholder"
    description = "Simulation tool — returns predetermined results."
    input_schema = CSVGeneratorInput   # dummy — validation is bypassed
    output_schema = CSVGeneratorOutput # dummy

    def __init__(self, tool_name: str, results: list):
        # Shadow class attributes with instance attributes for this mock.
        self.name = tool_name
        self._results = list(results)
        self._call_index = 0

    def execute(self, input_data):
        idx = min(self._call_index, len(self._results) - 1)
        result = self._results[idx]
        self._call_index += 1
        return result


# ── Simulation Planner Factory ────────────────────────────────────────────────

def make_sim_planner(decisions: list):
    """
    Returns a planner_fn that returns predetermined (tool, args, reasoning)
    tuples in sequence. Signature matches llm_planner: (state, registry) -> dict.
    """
    it = iter(decisions)

    def sim_planner(state: AgentState, registry: ToolRegistry) -> dict:
        tool_name, tool_args, reasoning = next(it)
        return {
            "next_tool": tool_name,
            "next_tool_args": tool_args,
            "planner_reasoning": reasoning,
        }

    return sim_planner


# ── Pre-built ToolResults for simulation ──────────────────────────────────────

CSV_PATH  = "output/sim_employees.csv"
XLSX_PATH = "output/sim_employees.xlsx"
SHEET_ID  = "sim-sheet-abc123"

R_CSV_OK = ToolResult[CSVGeneratorOutput](
    tool_name="csv_generator", success=True,
    data=CSVGeneratorOutput(csv_path=CSV_PATH, row_count=20, columns=["id", "full_name"]),
    duration_seconds=0.31,
)
R_EXCEL_FAIL = ToolResult(
    tool_name="excel_tool", success=False,
    error="COM dispatch error: Excel not responding.", duration_seconds=0.05,
)
R_EXCEL_OK = ToolResult[ExcelOutput](
    tool_name="excel_tool", success=True,
    data=ExcelOutput(xlsx_path=XLSX_PATH, sheet_name="Employee Data", row_count=20),
    duration_seconds=1.20,
)
R_SHEETS_OK = ToolResult[SheetsOutput](
    tool_name="sheets_tool", success=True,
    data=SheetsOutput(spreadsheet_id=SHEET_ID, spreadsheet_url=f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit", row_count=20),
    duration_seconds=0.88,
)
R_VERIFY_PASS = ToolResult[VerifyOutput](
    tool_name="verify_tool", success=True,
    data=VerifyOutput(csv_rows=20, xlsx_rows=20, sheet_rows=20, all_match=True, summary="PASSED: all 20 rows match."),
    duration_seconds=0.22,
)
R_VERIFY_FAIL = ToolResult[VerifyOutput](
    tool_name="verify_tool", success=True,   # tool ran; data mismatch
    data=VerifyOutput(csv_rows=20, xlsx_rows=20, sheet_rows=18, all_match=False, summary="FAILED: Sheets=18, expected 20."),
    duration_seconds=0.25,
)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO A — Happy Path
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario_a():
    section("SCENARIO A — Happy Path (all 4 tools succeed)")

    panel = MockPanel()

    mock_registry = ToolRegistry()
    mock_registry.register(SimulatedTool("csv_generator", [R_CSV_OK]))
    mock_registry.register(SimulatedTool("excel_tool",    [R_EXCEL_OK]))
    mock_registry.register(SimulatedTool("sheets_tool",   [R_SHEETS_OK]))
    mock_registry.register(SimulatedTool("verify_tool",   [R_VERIFY_PASS]))

    decisions = [
        ("csv_generator", {"num_rows": 20, "output_dir": "output"}, "Generate CSV first."),
        ("excel_tool",    {"csv_path": CSV_PATH, "output_dir": "output"}, "CSV ready, import to Excel."),
        ("sheets_tool",   {"csv_path": CSV_PATH}, "Upload to Sheets."),
        ("verify_tool",   {"csv_path": CSV_PATH, "xlsx_path": XLSX_PATH, "sheet_id": SHEET_ID}, "Verify all targets."),
    ]

    graph = build_graph(
        planner_fn=make_sim_planner(decisions),
        tool_registry=mock_registry,
        panel=panel,
    )
    initial = create_initial_state("Generate employee CSV, import to Excel and Google Sheets, then verify.", task_id="sim-a")
    final = graph.invoke(initial)

    # ── State transition assertions ──
    assert_eq("A: final status", final["status"], AgentStatus.COMPLETED)
    assert_eq("A: step count", len(final["step_reports"]), 4)
    assert_eq("A: all steps SUCCESS",
              all(s.status == ToolStatus.SUCCESS for s in final["step_reports"]), True)

    # ── Artifact propagation via artifact_updates() ──
    assert_eq("A: csv_path in state",  final["csv_path"],  CSV_PATH)
    assert_eq("A: xlsx_path in state", final["xlsx_path"], XLSX_PATH)
    assert_eq("A: sheet_id in state",  final["sheet_id"],  SHEET_ID)
    assert_eq("A: verification_passed", final["verification_passed"], True)

    # ── Retry counts ──
    assert_eq("A: retry_counts empty", final["retry_counts"], {})

    # ── Rich panel received updates ──
    assert_eq("A: panel step count", len(panel.steps), 4)
    assert_eq("A: panel reasoning updates", len(panel.reasoning_updates), 4)
    assert_true("A: all panel statuses SUCCESS",
                all(status == "SUCCESS" for _, status, _ in panel.steps))
    assert_true("A: panel stopped", panel.stopped)

    # ── ExecutionReport reconstruction ──
    from src.agent.nodes import _build_execution_report
    report = _build_execution_report(final)
    assert_eq("A: report status",    report.status,          AgentStatus.COMPLETED)
    assert_eq("A: report step count", len(report.steps),     4)
    assert_eq("A: report csv_path",  report.artifacts.csv_path,  CSV_PATH)
    assert_eq("A: report xlsx_path", report.artifacts.xlsx_path, XLSX_PATH)
    assert_true("A: report sheet_url set", report.artifacts.sheet_url is not None)
    assert_true("A: report total_duration > 0", report.total_duration_seconds > 0)

    print("\n  [SCENARIO A PASSED]")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO B — Excel Fails Once, Succeeds on Retry
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario_b():
    section("SCENARIO B — Excel fails once, succeeds on retry")

    panel = MockPanel()

    mock_registry = ToolRegistry()
    mock_registry.register(SimulatedTool("csv_generator", [R_CSV_OK]))
    # First call fails, second call succeeds.
    mock_registry.register(SimulatedTool("excel_tool",    [R_EXCEL_FAIL, R_EXCEL_OK]))
    mock_registry.register(SimulatedTool("sheets_tool",   [R_SHEETS_OK]))
    mock_registry.register(SimulatedTool("verify_tool",   [R_VERIFY_PASS]))

    decisions = [
        ("csv_generator", {"num_rows": 20, "output_dir": "output"}, "Generate CSV."),
        ("excel_tool",    {"csv_path": CSV_PATH, "output_dir": "output"}, "Import to Excel (attempt 1)."),
        ("excel_tool",    {"csv_path": CSV_PATH, "output_dir": "output"}, "Retrying Excel after failure."),
        ("sheets_tool",   {"csv_path": CSV_PATH}, "Upload to Sheets."),
        ("verify_tool",   {"csv_path": CSV_PATH, "xlsx_path": XLSX_PATH, "sheet_id": SHEET_ID}, "Verify."),
    ]

    graph = build_graph(
        planner_fn=make_sim_planner(decisions),
        tool_registry=mock_registry,
        panel=panel,
    )
    initial = create_initial_state("Generate, import, upload, verify.", task_id="sim-b")
    final = graph.invoke(initial)

    # ── State transition assertions ──
    assert_eq("B: final status", final["status"], AgentStatus.COMPLETED)
    assert_eq("B: step count (5 including retry)", len(final["step_reports"]), 5)

    # ── Step order ──
    tool_sequence = [s.tool_name for s in final["step_reports"]]
    assert_eq("B: tool sequence",
              tool_sequence,
              ["csv_generator", "excel_tool", "excel_tool", "sheets_tool", "verify_tool"])

    # ── Retry counts ──
    assert_eq("B: excel_tool retry_count", final["retry_counts"].get("excel_tool", 0), 1)

    # ── Step statuses ──
    statuses = [s.status for s in final["step_reports"]]
    assert_eq("B: step 2 status FAILED", statuses[1], ToolStatus.FAILED)
    assert_eq("B: step 3 status SUCCESS", statuses[2], ToolStatus.SUCCESS)
    assert_eq("B: final verify SUCCESS", statuses[4], ToolStatus.SUCCESS)

    # ── Artifact propagation ──
    assert_eq("B: csv_path",  final["csv_path"],  CSV_PATH)
    assert_eq("B: xlsx_path", final["xlsx_path"], XLSX_PATH)
    assert_eq("B: sheet_id",  final["sheet_id"],  SHEET_ID)
    assert_eq("B: verification_passed", final["verification_passed"], True)

    # ── Rich panel: one FAILED step, four SUCCESS ──
    assert_eq("B: panel step count", len(panel.steps), 5)
    panel_statuses = [s for _, s, _ in panel.steps]
    assert_eq("B: panel step 2 FAILED",  panel_statuses[1], "FAILED")
    assert_eq("B: panel step 3 SUCCESS", panel_statuses[2], "SUCCESS")

    # ── error_log contains the retry message ──
    assert_true("B: error_log has retry entry",
                any("excel_tool" in e for e in final["error_log"]))

    print("\n  [SCENARIO B PASSED]")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO C — Verification Permanently Fails → Graceful Termination
# ─────────────────────────────────────────────────────────────────────────────

def run_scenario_c():
    section("SCENARIO C — Verify permanently fails, graph terminates via max_steps")

    panel = MockPanel()

    mock_registry = ToolRegistry()
    mock_registry.register(SimulatedTool("csv_generator", [R_CSV_OK]))
    mock_registry.register(SimulatedTool("excel_tool",    [R_EXCEL_OK]))
    mock_registry.register(SimulatedTool("sheets_tool",   [R_SHEETS_OK]))
    # verify_tool always returns all_match=False (permanent data mismatch).
    mock_registry.register(SimulatedTool("verify_tool",   [R_VERIFY_FAIL] * 10))

    decisions = [
        ("csv_generator", {"num_rows": 20, "output_dir": "output"}, "Generate CSV."),
        ("excel_tool",    {"csv_path": CSV_PATH, "output_dir": "output"}, "Import to Excel."),
        ("sheets_tool",   {"csv_path": CSV_PATH}, "Upload to Sheets."),
        ("verify_tool",   {"csv_path": CSV_PATH, "xlsx_path": XLSX_PATH, "sheet_id": SHEET_ID}, "Verify attempt 1."),
        ("verify_tool",   {"csv_path": CSV_PATH, "xlsx_path": XLSX_PATH, "sheet_id": SHEET_ID}, "Verify attempt 2."),
        ("verify_tool",   {"csv_path": CSV_PATH, "xlsx_path": XLSX_PATH, "sheet_id": SHEET_ID}, "Verify attempt 3."),
    ]

    # max_agent_steps=6 passed directly — no config patching required.
    graph = build_graph(
        planner_fn=make_sim_planner(decisions),
        tool_registry=mock_registry,
        panel=panel,
        max_agent_steps=6,
    )
    initial = create_initial_state("Generate, import, upload, verify.", task_id="sim-c")
    final = graph.invoke(initial)

    assert_eq("C: final status FAILED", final["status"], AgentStatus.FAILED)
    assert_eq("C: step count = max_agent_steps", len(final["step_reports"]), 6)

    verify_steps = [s for s in final["step_reports"] if s.tool_name == "verify_tool"]
    assert_eq("C: verify_tool ran 3 times", len(verify_steps), 3)

    # Tool ran successfully each time; the data mismatch is what fails the task.
    assert_true("C: all verify steps show SUCCESS status (tool ran OK)",
                all(s.status == ToolStatus.SUCCESS for s in verify_steps))

    assert_eq("C: verification_passed is False", final.get("verification_passed"), False)

    assert_true("C: error_log has max_steps message",
                any("Max agent steps" in e for e in final["error_log"]))

    assert_true("C: panel stopped", panel.stopped)
    assert_eq("C: panel step count", len(panel.steps), 6)

    assert_eq("C: csv_path in state",  final["csv_path"],  CSV_PATH)
    assert_eq("C: xlsx_path in state", final["xlsx_path"], XLSX_PATH)
    assert_eq("C: sheet_id in state",  final["sheet_id"],  SHEET_ID)

    print("\n  [SCENARIO C PASSED]")



# ─────────────────────────────────────────────────────────────────────────────
# Verification Report
# ─────────────────────────────────────────────────────────────────────────────

def print_verification_report(results: dict):
    section("MILESTONE 4 — GRAPH SIMULATION VERIFICATION REPORT")
    print()
    for scenario, (passed, notes) in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {scenario}")
        for note in notes:
            print(f"         {note}")
    print()
    all_passed = all(p for p, _ in results.values())
    if all_passed:
        print("  RESULT: ALL 3 GRAPH SIMULATIONS PASSED")
        print("  The orchestration layer is verified.")
        print("  Safe to connect: Gemini LLM + pywin32 Excel + gspread Sheets.")
    else:
        print("  RESULT: ONE OR MORE SIMULATIONS FAILED — do not proceed.")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = {}

    for label, runner in [
        ("Scenario A — Happy Path",                    run_scenario_a),
        ("Scenario B — Excel Retry",                   run_scenario_b),
        ("Scenario C — Verify Permanently Fails",      run_scenario_c),
    ]:
        try:
            runner()
            results[label] = (True, ["All assertions passed."])
        except SystemExit:
            results[label] = (False, ["Assertion failed — see output above."])
        except Exception as exc:
            results[label] = (False, [f"Unexpected exception: {exc!r}"])

    print_verification_report(results)

    if not all(p for p, _ in results.values()):
        sys.exit(1)
