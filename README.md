# Autonomous AI Agent

An autonomous, LangGraph-powered AI agent that orchestrates a full data pipeline — generating employee records, exporting to Excel, uploading to Google Sheets, and cross-validating all three targets to confirm data integrity.

> **Built with:** LangGraph · Groq (`llama-3.3-70b-versatile`) · Google Sheets API v4 · Microsoft Excel COM · Faker · Python 3.11

---

## Features

| Feature | Details |
|---|---|
| **AI Planner** | LLM-driven step-by-step orchestration via LangGraph |
| **LLM Backend** | Groq (primary, fast & free) → OpenRouter → Google Gemini (tiered fallback) |
| **CSV Generation** | 20 realistic employee records via Faker |
| **Excel Automation** | Native COM automation — real `.xlsx` with formatted headers |
| **Google Sheets Upload** | Sheets API v4 via OAuth Desktop Flow — auto-creates a new sheet if needed |
| **Verification** | Cross-validates row counts across CSV, Excel, and Google Sheets |
| **Structured Logging** | Per-node timing, artifact tracking, and JSON report on every run |
| **Retry Logic** | Configurable retries per tool, max step ceiling, and graceful error handling |

### Bonus Features

| Bonus | Details |
|---|---|
| **Docker Support** | Production-ready `Dockerfile` + `docker-compose.yml` (see below) |
| **Tiered LLM Routing** | Groq → OpenRouter → Gemini, fully configurable via `.env` |
| **Auto-create Sheet** | If configured sheet is not writable, a new one is provisioned automatically |
| **OAuth Desktop Flow** | No service account required — authenticates as the end user |

---

## Platform Requirements

> [!IMPORTANT]
> **Excel COM automation requires Windows with Microsoft Excel installed.**
> The `excel_tool` uses `win32com.client` (pywin32), which is a Windows-only library.
> On Linux/macOS (including Docker), the `excel_tool` step will fail gracefully —
> the agent's error handler catches it and the pipeline continues.

---

## Architecture Overview

```
                         ┌─────────────────────────────────┐
                         │         LangGraph StateGraph      │
                         └─────────────────────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │       Planner        │  ◄── Groq / OpenRouter / Gemini
                              │   (LLM Decision)     │
                              └──────────┬──────────┘
                                         │  next_tool
                              ┌──────────▼──────────┐
                              │       Executor       │  ◄── ToolRegistry.get(tool)
                              └──────────┬──────────┘
                          success ◄──────┴──────► failure
                              │                        │
              ┌───────────────▼───┐        ┌──────────▼──────────┐
              │  Completion Check  │        │    Error Handler     │
              └───────────────┬───┘        └──────────┬──────────┘
                    done │    │ continue      retry │  │ max retries
                         │    └─────────────────────┘  │
                         │                             │
                ┌─────────▼──────────────────────────▼───┐
                │               Reporter                   │
                │         (JSON report + summary)          │
                └─────────────────────────────────────────┘
```

**Tool execution order (enforced by planner):**

```
csv_generator → excel_tool → sheets_tool → verify_tool
```

For a full deep-dive, see [`docs/architecture.md`](docs/architecture.md).

---

## Project Structure

```
agent_project/
├── main.py                      # Production entry point
├── setup_oauth.py               # One-time OAuth setup helper
├── requirements.txt             # All Python dependencies
├── Dockerfile                   # Docker image definition
├── docker-compose.yml           # Docker Compose runtime config
├── .env.example                 # Environment variable template
├── .gitignore
│
├── credentials/                 # OAuth secrets (git-ignored)
│   ├── credentials.json         # Downloaded from GCP Console
│   └── token.json               # Auto-created on first OAuth run
│
├── output/                      # Generated files (git-ignored)
│   ├── employees_<hash>.csv
│   ├── employees_<hash>.xlsx
│   └── <task_id>_report.json
│
├── src/
│   ├── agent/
│   │   ├── graph.py             # LangGraph StateGraph compiler
│   │   └── nodes.py             # All 5 node factories + routing functions
│   ├── core/
│   │   ├── auth.py              # OAuth Desktop Flow (token caching)
│   │   ├── config.py            # pydantic-settings AppConfig
│   │   ├── exceptions.py        # Typed exception hierarchy
│   │   └── logger.py            # structlog configuration
│   ├── models/
│   │   └── schemas.py           # AgentState, ToolResult, all I/O DTOs
│   └── tools/
│       ├── base.py              # Generic BaseTool[InputT, OutputT]
│       ├── registry.py          # ToolRegistry singleton
│       ├── csv_generator/       # Faker-based CSV generation
│       ├── excel_tool/          # pywin32 COM Excel automation (Windows only)
│       ├── sheets_tool/         # Google Sheets API v4 upload
│       └── verify_tool/         # Cross-target row count validation
│
├── tests/
│   └── integration/
│       ├── run_all.py           # Run all integration tests
│       ├── test_01_csv.py
│       ├── test_02_excel.py
│       ├── test_03_gemini_planner.py
│       ├── test_04_sheets.py
│       └── test_05_verify.py
│
└── docs/
    ├── architecture.md          # Deep-dive technical design
    └── production_readiness.md  # Pre-demo checklist
```

---

## Setup Instructions

### 1. Clone and Install

```bash
git clone <repo-url>
cd agent_project
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Open `.env` and fill in your keys. At minimum:

```ini
GROQ_API_KEY=gsk_...        # Primary LLM — get free at console.groq.com
GOOGLE_API_KEY=AIza...      # Fallback LLM — Google AI Studio
GOOGLE_SHEET_ID=1abc...     # Any spreadsheet ID (or leave default)
```

### 3. GCP Project Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create or select a project
3. Enable the **Google Sheets API**:
   `APIs & Services → Enable APIs → Google Sheets API → Enable`
4. Create **OAuth 2.0 Desktop credentials**:
   `APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app`
5. Download the JSON file and save it as `credentials/credentials.json`

### 4. OAuth Setup (One-time)

```bash
python setup_oauth.py
```

- A browser window will open
- Select your Google account
- Click **Allow** on the consent screen
- `credentials/token.json` is saved and reused on all future runs

> [!TIP]
> If you see "Google hasn't verified this app" → click **Advanced** → **Go to (unsafe)** → **Allow**

### 5. Run the Agent

```bash
python main.py
```

You can also pass a custom prompt:

```bash
python main.py "Generate 30 employee records, import to Excel, upload to Sheets, verify."
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | **Recommended** | — | Primary LLM (fast, free). Get from [console.groq.com](https://console.groq.com) |
| `GOOGLE_API_KEY` | Yes* | — | Fallback LLM. From [aistudio.google.com](https://aistudio.google.com) |
| `OPENROUTER_API_KEY` | No | — | Secondary fallback. From [openrouter.ai](https://openrouter.ai) |
| `GOOGLE_SHEET_ID` | Yes | — | Target spreadsheet ID from the sheet URL |
| `GOOGLE_CREDENTIALS_PATH` | No | `credentials/credentials.json` | Path to OAuth Desktop JSON |
| `GOOGLE_TOKEN_PATH` | No | `credentials/token.json` | Path to cached OAuth token |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model name |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model name |
| `MAX_AGENT_STEPS` | No | `15` | Safety ceiling on LangGraph loop iterations |
| `MAX_TOOL_RETRIES` | No | `2` | Max retries per failing tool |
| `OUTPUT_DIR` | No | `output` | Directory for generated CSV/XLSX files |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_FORMAT` | No | `console` | Log format: `console` or `json` |

*`GOOGLE_API_KEY` is required unless `GROQ_API_KEY` is set (Groq takes priority).

---

## Example Prompts

The default prompt runs the full pipeline with 20 rows:

```
Generate a CSV file with 20 realistic employee records, import it into
Microsoft Excel with professional formatting, upload it to Google Sheets,
then verify that all three targets contain exactly the same number of data rows.
```

You can customise via CLI:

```bash
# 30-row dataset
python main.py "Generate 30 employee records, format in Excel, upload to Sheets, verify."

# Explicit task description
python main.py "Create employee data CSV, convert to Excel, sync to Google Sheets, cross-validate."
```

---

## Docker (Bonus)

> [!NOTE]
> Docker support is provided as a bonus deployment option.
> **Excel COM automation is Windows-only** and will not function inside a Linux container.
> All other steps (CSV generation, Sheets upload, verification) work correctly in Docker.

### Build

```bash
docker build -t autonomous-agent .
```

### Run with Docker Compose (recommended)

```bash
docker-compose up
```

This mounts your local `.env`, `credentials/`, and `output/` into the container — no secrets are baked into the image.

### Run manually

```bash
docker run --rm \
  -v "$(pwd)/.env:/app/.env:ro" \
  -v "$(pwd)/credentials:/app/credentials" \
  -v "$(pwd)/output:/app/output" \
  autonomous-agent
```

---

## Troubleshooting

### `GOOGLE_API_KEY` not set / quota exhausted
Set `GROQ_API_KEY` in `.env` — Groq is free and has no daily quota limits on the free tier.

### `403: The caller does not have permission` on Google Sheets
The agent automatically creates a new spreadsheet instead of writing to the configured one. The new sheet URL is printed at the end of each run.

### `Google Sheets API has not been used in project...`
Enable the Sheets API in your GCP project:
`console.cloud.google.com → APIs & Services → Google Sheets API → Enable`

### `credentials/credentials.json not found`
Download OAuth Desktop credentials from GCP Console and place the file at `credentials/credentials.json`. Run `python setup_oauth.py` after.

### OAuth browser window doesn't open
Run `setup_oauth.py` directly — it handles the full browser flow. After it completes, `python main.py` will run without any browser interaction.

### Excel step fails on non-Windows / in Docker
Expected. `excel_tool` requires Windows + Microsoft Excel. On Linux, the error handler catches it and continues the pipeline. The CSV and Sheets steps succeed.

### `UnicodeEncodeError` on Windows terminal
The agent forces UTF-8 on stdout at startup. If you see this, ensure your terminal supports UTF-8 (Windows Terminal recommended over `cmd.exe`).

---

## Output Files & Sample Output

Each run produces:

| File | Description |
|---|---|
| `output/employees_<hash>.csv` | Raw synthetic employee data |
| `output/employees_<hash>.xlsx` | Formatted Excel workbook |
| `output/<task_id>_report.json` | Full execution audit trail (JSON) |
| Google Sheet URL | Printed in terminal on every successful run |

**Sample Terminal Output on Success:**
```text
─────────────────────────────── Agent COMPLETED ───────────────────────────────
Steps completed: 4
  OK Step 1: csv_generator (0.016s)
  OK Step 2: excel_tool (5.125s)
  OK Step 3: sheets_tool (6.313s)
  OK Step 4: verify_tool (1.671s)

CSV:   output\employees_1e727d92.csv
XLSX:  output\employees_1904aebb.xlsx
Sheet: https://docs.google.com/spreadsheets/d/1XROUH...

Verification PASSED - all targets match.
```

---

## Screenshots

> *Demo run terminal output:*
> ![Terminal output placeholder](docs/screenshots/terminal_run.png)

> *Excel workbook with formatted headers:*
> ![Excel screenshot placeholder](docs/screenshots/excel_output.png)

> *Google Sheet populated with agent data:*
> ![Google Sheet screenshot placeholder](docs/screenshots/sheets_output.png)

---

## Future Improvements

While this agent successfully completes the end-to-end data pipeline, potential future improvements include:
- **Linux Excel Fallback:** Replacing the `win32com` COM automation with `openpyxl` formatting capabilities to make the entire pipeline fully cross-platform (including in Docker).
- **Streaming UI:** Emitting LangGraph tokens directly to the console for real-time planner reasoning visibility.
- **Human-in-the-Loop (HITL):** Adding a checkpoint in LangGraph before the Sheets upload to allow a human to review the Excel file and approve the upload.

---

## License

MIT
