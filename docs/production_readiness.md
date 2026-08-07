# Production Readiness

This document outlines the operational and production-ready characteristics of the autonomous agent pipeline.

## 1. Error Handling & Retry Logic

The agent employs a multi-tiered approach to reliability.

### LangGraph Level (`max_tool_retries`)
If any tool execution fails (e.g., network timeout, COM automation crash), the `error_handler` node catches it. It tracks retry counts in the global `AgentState` and automatically routes back to the LLM Planner for another attempt. 
- By default, `MAX_TOOL_RETRIES=2` per tool. 
- The LLM receives the error message in the context block and can adjust its strategy if applicable.

### Graph Safety Ceiling (`max_agent_steps`)
To prevent infinite reasoning loops (where the LLM continuously hallucinates a bad tool or fails repeatedly without exceeding per-tool limits), the `completion_check` node enforces a strict ceiling.
- By default, `MAX_AGENT_STEPS=15`. If exceeded, the agent forcefully aborts and marks the graph as `FAILED`.

### Sheets API Fallback
A common production failure in Google Sheets integrations is `403 PERMISSION_DENIED` (the configured Sheet ID exists, but the authenticated user only has Viewer access). 
- **Implementation:** The `SheetsTool` intercepts this error specifically. Rather than failing the pipeline, it automatically provisions a brand new Google Spreadsheet owned by the OAuth user, uploads the data there, and returns the new URL.

## 2. Observability & Logging

### Structured Logging (structlog)
All logs are emitted using `structlog`.
- `LOG_FORMAT=console`: Emits beautiful, colorized, human-readable logs for local development.
- `LOG_FORMAT=json`: Emits strict JSON lines suitable for ingestion by Datadog, ELK, or CloudWatch in a production environment.

### Node Boundary Timing
Every LangGraph node logs a `duration_s` metric on completion, enabling easy bottleneck analysis across the planner and executor phases.

### Audit Trails
Every execution (whether `SUCCESS` or `FAILED`) concludes with the `reporter` node dumping the complete `AgentState` into a JSON artifact at `output/<task_id>_report.json`. This provides an immutable audit trail of the LLM's reasoning, the tools executed, their durations, and any errors encountered.

## 3. Security Considerations

### No Hardcoded Secrets
The `.gitignore` and `.dockerignore` files aggressively filter out `.env` files and the entire `credentials/` directory.

### OAuth Desktop Flow vs Service Accounts
The project uses the Google OAuth Desktop flow rather than Service Accounts.
- **Why?** Service Accounts can introduce massive security risks if leaked, and often trigger Google Workspace domain-wide restrictions. By using the Desktop flow, the agent acts strictly on behalf of the end-user. If the token is compromised, it only affects that user and can be instantly revoked.

### Local Execution Only
The LLM execution environment (LangChain / LangGraph) does not execute arbitrary code (`PythonREPLTool`). It is strictly constrained to the 4 explicit, statically defined tools in the `ToolRegistry`.

## 4. Performance

- **Tiered LLM Routing:** Generating structured JSON from an LLM can be slow on free tiers. The agent prioritizes the Groq API (`llama-3.3-70b-versatile`), which provides near-instantaneous inference (often <2 seconds per planning step). It falls back to OpenRouter or Google Gemini if Groq is unavailable.
- **Dependency Caching:** The Docker image utilizes layered caching, installing the hefty Python requirements before copying source code, ensuring instant rebuilds during active development.
- **COM Teardown:** The `ExcelTool` strictly guarantees Microsoft Excel COM application teardown (`wb.Close()`, `excel.Quit()`, `CoUninitialize()`) via `finally` blocks, preventing zombie `EXCEL.EXE` processes from locking up the host machine's memory.

## 5. Deployment Notes

- **Docker:** The provided `Dockerfile` and `docker-compose.yml` are production-ready.
- **Platform Limitation:** The `ExcelTool` depends on `win32com`, meaning the full 4-tool pipeline **must** be deployed on a Windows host or Windows Server container with Microsoft Office installed. Deploying to a Linux container (via the provided `Dockerfile`) is fully supported by the codebase, but the `excel_tool` step will intentionally fail and be skipped by the orchestrator.
