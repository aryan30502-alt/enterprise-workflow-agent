# End-to-End Walkthrough

This document breaks down a successful execution of the autonomous pipeline. It serves as an explanation of the agent's behavior and can be used as a script for a live demo.

## Execution Trigger
The user runs:
```bash
python main.py
```
*No prompt is provided, so the agent falls back to its default instruction: "Generate a CSV file with 20 realistic employee records, import it into Microsoft Excel with professional formatting, upload it to Google Sheets, then verify that all three targets contain exactly the same number of data rows."*

## Startup & Authentication
1. **OAuth Check:** The agent first verifies `credentials/token.json`. If valid, it silently authenticates. If not, it opens the browser for the user to log in.
2. **Tool Registration:** The agent dynamically loads the 4 tools (`csv_generator`, `excel_tool`, `sheets_tool`, `verify_tool`) into the `ToolRegistry`.
3. **Graph Initialization:** LangGraph starts and creates task `aa5ce18a`.

---

## Step 1: Planning
The LangGraph state moves to the `planner` node.
- The planner (powered by Groq `llama-3.3-70b-versatile`) evaluates the goal.
- **LLM Reasoning:** *"I need to generate a CSV file with 20 employee records first. I will use the `csv_generator` tool."*
- **Action:** The planner sets `next_tool = csv_generator`.

## Step 2: CSV Generation
The graph routes to the `executor` node.
- **Execution:** The executor invokes `csv_generator`.
- **Under the hood:** The tool uses the `Faker` library to generate 20 records (ID, Name, Email, Department, Salary, Hire Date, Phone). Emails are guaranteed unique.
- **Output:** Saves to `output/employees_1e727d92.csv`.
- **State Update:** The executor merges the `csv_path` artifact into the global state.

---

## Step 3: Planning
The graph loops back to the `planner` node.
- **LLM Reasoning:** *"The CSV has been generated at `output/employees_1e727d92.csv`. Now I need to import it into Excel and format it. I will use the `excel_tool`."*
- **Action:** The planner sets `next_tool = excel_tool`.

## Step 4: Excel Formatting
The graph routes to the `executor` node.
- **Execution:** The executor invokes `excel_tool`, passing the `csv_path` as an argument.
- **Under the hood:** The tool launches Microsoft Excel silently via COM (`win32com`). It imports the CSV, bolds and centers the headers, applies a blue background, autofits all columns, and saves the file as an `.xlsx`. It then cleanly shuts down the Excel process.
- **Output:** Saves to `output/employees_1904aebb.xlsx`.
- **State Update:** The executor merges the `xlsx_path` artifact into the global state.

---

## Step 5: Planning
The graph loops back to the `planner` node.
- **LLM Reasoning:** *"The Excel file is ready. I now need to upload the CSV data to Google Sheets. I will use the `sheets_tool`."*
- **Action:** The planner sets `next_tool = sheets_tool`.

## Step 6: Google Sheets Upload
The graph routes to the `executor` node.
- **Execution:** The executor invokes `sheets_tool`.
- **Under the hood:** 
  1. The tool authenticates via the Sheets API v4.
  2. It notices the configured `GOOGLE_SHEET_ID` in `.env` is read-only for this user.
  3. *Fallback triggered:* It automatically provisions a brand new Spreadsheet named "Employee Data - Agent Import".
  4. It uploads all 20 rows of data in a single batch request.
- **Output:** Returns the URL to the new Google Sheet.
- **State Update:** The executor merges the `sheet_id` artifact into the global state.

---

## Step 7: Planning
The graph loops back to the `planner` node.
- **LLM Reasoning:** *"All targets are populated. I must now verify that the row counts match across the CSV, the Excel file, and the Google Sheet. I will use the `verify_tool`."*
- **Action:** The planner sets `next_tool = verify_tool`.

## Step 8: Verification
The graph routes to the `executor` node.
- **Execution:** The executor invokes `verify_tool`.
- **Under the hood:** The tool reads the local CSV, opens the local `.xlsx` using `openpyxl`, and queries the Google Sheets API. It counts the data rows (excluding headers) in all three.
- **Result:** `csv_rows = 20`, `xlsx_rows = 20`, `sheet_rows = 20`. `all_match = True`.
- **State Update:** The executor merges `verification_passed = True` into the global state.

---

## Step 9: Completion
The graph routes to the `completion_check` node.
- **Evaluation:** Because `verification_passed == True`, the node marks the agent status as `COMPLETED` and routes to the terminal `reporter` node.

## Step 10: Reporting
- The `reporter` dumps the full execution history (including LLM prompts, durations, and artifact paths) into `output/aa5ce18a_report.json`.
- The rich terminal UI outputs the final summary:

```text
─────────────────────────────── Agent COMPLETED ───────────────────────────────
Steps completed: 4
  OK Step 1: csv_generator (0.016s)
  OK Step 2: excel_tool (5.125s)
  OK Step 3: sheets_tool (6.313s)
  OK Step 4: verify_tool (1.671s)

CSV:   output\employees_1e727d92.csv
XLSX:  output\employees_1904aebb.xlsx
Sheet: https://docs.google.com/spreadsheets/d/1XROUHvLpQ7gML0F7QLhsphDEhUVf1eQHXlg8o38HYHE/edit

Verification PASSED - all targets match.
```
*Total execution time: ~13 seconds.*
