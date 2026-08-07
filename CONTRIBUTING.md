# Contributing

First off, thank you for considering contributing to the Autonomous AI Agent! 

## Local Setup

1. Fork and clone the repository.
2. Ensure you have Python 3.11+ installed.
3. Create a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   ```
4. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
5. Follow the `README.md` to set up your `.env` and OAuth credentials.

## Coding Standards

- **Type Hints:** All functions and methods must have complete type annotations. We rely heavily on Pydantic for validation, so ensure inputs and outputs conform to schemas in `src/models/schemas.py`.
- **Tool Architecture:** Any new tool must inherit from `BaseTool[InputT, OutputT]`. Tools must never raise exceptions that crash the LangGraph loop—catch errors internally and return `success=False` in the `ToolResult`.
- **Logging:** Do not use standard `print()` statements. Use the configured `structlog` logger imported via `src.core.logger.get_logger()`.
- **Cross-Platform:** Avoid hardcoding Windows-specific paths. If a tool is platform-specific (like `excel_tool` using `win32com`), ensure it is wrapped in an OS check or gracefully fails so the error handler can catch it on Linux/macOS.

## Adding a New Tool

1. Create a new directory under `src/tools/` (e.g., `src/tools/my_tool/`).
2. Implement your tool by inheriting `BaseTool`.
3. Register your tool in `main.py` by calling `ToolRegistry.register(MyTool())` before compiling the graph.
4. Update the LLM planner prompt in `src/agent/nodes.py` to make the agent aware of the tool's purpose.

## Running Tests

Integration tests are located in `tests/integration/`. To run them all sequentially:

```bash
python -m unittest tests/integration/run_all.py
```

To run a specific test suite:

```bash
python -m unittest tests/integration/test_01_csv.py
```
