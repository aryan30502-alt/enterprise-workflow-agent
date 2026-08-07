# Architecture Overview

This document outlines the architecture of the LangGraph-based autonomous agent pipeline.

## 1. LangGraph StateGraph

The agent's execution loop is orchestrated by **LangGraph**, providing a deterministic state machine that ensures reliability, observability, and strict sequential execution.

### Graph Topology

```
                         START
                           │
                           ▼
                    ┌─────────────┐
        ┌───────────│   planner   │──────────────┐
        │           └─────────────┘              │
        │                  │                     │
        │                  ▼                     │
        │           ┌─────────────┐              │
        │           │  executor   │              │
        │           └─────────────┘              │
        │             │          │               │
        │         success      failure           │
        │             │          │               │
        │             ▼          ▼               │
        │   ┌────────────────┐ ┌───────────────┐ │
        │   │completion_check│ │ error_handler │ │
        │   └────────────────┘ └───────────────┘ │
        │      │          │       │          │   │
        │   continue     done   retry     failed │
        │      │          │       │          │   │
        └──────┴──────────┼───────┘          │   │
                          ▼                  ▼   ▼
                    ┌──────────────────────────────┐
                    │           reporter           │
                    └──────────────────────────────┘
                                   │
                                   ▼
                                  END
```

### 1.1 `planner` (The Brain)
- Driven by the LLM (Groq / OpenRouter / Gemini).
- Given the `AgentState` (which includes completed steps, artifacts, and errors), the planner determines the `next_tool` to call.
- The LLM enforces the specific pipeline sequence: `csv_generator` → `excel_tool` → `sheets_tool` → `verify_tool`.

### 1.2 `executor` (The Muscle)
- Takes the `next_tool` from the planner and invokes it via the `ToolRegistry`.
- Merges the tool's execution result back into the global state.
- Entirely generic—it does not know the names of the tools it is running, it just invokes `result.data.artifact_updates()` to populate the graph's state.

### 1.3 `error_handler` (The Shield)
- If a tool fails, execution routes here.
- Tracks `retry_counts`. If a tool hasn't hit `MAX_TOOL_RETRIES`, it routes back to the planner to try again.
- If it exceeds max retries, it marks the graph as `FAILED` and routes to the `reporter`.

### 1.4 `completion_check` (The Watchdog)
- Validates if the pipeline is finished (e.g., `verification_passed == True`).
- Ensures the loop hasn't exceeded `MAX_AGENT_STEPS` (preventing infinite loops).

### 1.5 `reporter` (The Audit)
- Terminal node.
- Dumps the final `AgentState` into a detailed JSON execution report saved in the `output/` directory.

## 2. Tool Architecture

Tools are strictly separated from the LangGraph orchestration.

### `BaseTool`
All tools inherit from `BaseTool[InputT, OutputT]`. This provides a consistent SDK-like interface. Tools **never raise exceptions** to the graph; they catch their own errors and return a `ToolResult` with `success=False`.

### `ToolRegistry`
The registry is a singleton loaded at startup. It acts as the single source of truth for tool availability and provides the JSON schemas that the LLM planner uses to understand how to call them.

## 3. Data Flow

1. **CSVGeneratorTool**: Uses `Faker` to generate 20 records. Returns `csv_path`.
2. **ExcelTool**: Takes `csv_path`. Opens Microsoft Excel via COM automation, applies headers and formatting, saves as `.xlsx`. Returns `xlsx_path`.
3. **SheetsTool**: Takes `csv_path`. Validates OAuth credentials via the Desktop Flow. Creates a new Google Spreadsheet via Sheets API v4. Uploads all rows in one batch update. Returns `sheet_id`.
4. **VerifyTool**: Takes `csv_path`, `xlsx_path`, and `sheet_id`. Independently queries all three sources to count data rows. Returns `verification_passed=True` if all counts match.

The executor merges the outputs of each tool into the global `AgentState`, making those paths available to the planner for the subsequent steps.
