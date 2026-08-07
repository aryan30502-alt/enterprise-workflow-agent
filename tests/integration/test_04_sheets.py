"""
Integration Test 4: SheetsTool — real gspread upload to Google Sheets.

Prerequisites:
  - credentials/service_account.json present
  - GOOGLE_SHEET_ID set in .env to a real spreadsheet ID
  - Service Account email has Editor access to that spreadsheet

Verifies:
  - SheetsTool authenticates without error
  - All 20 data rows + header are uploaded
  - The spreadsheet URL is returned correctly
  - artifact_updates() returns the spreadsheet_id
  - Uploaded data is readable back from the API
"""

import os
import sys
import pathlib

sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
CREDS_PATH = pathlib.Path(os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials/service_account.json"))

if not CREDS_PATH.exists():
    print("\n  [SKIP] credentials/service_account.json not found.")
    print("  Place your Service Account JSON at credentials/service_account.json")
    sys.exit(0)

if not GOOGLE_SHEET_ID or GOOGLE_SHEET_ID == "your_spreadsheet_id_here":
    print("\n  [SKIP] GOOGLE_SHEET_ID not configured in .env")
    print("  Set GOOGLE_SHEET_ID=<real sheet id> in .env to run this test.")
    sys.exit(0)


def ok(msg):  print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}"); sys.exit(1)
def section(t): print(f"\n{'='*55}\n  {t}\n{'='*55}")


section("INTEGRATION 4: SheetsTool (real gspread upload)")

# ── Step 1: Generate a real CSV ───────────────────────────────────────────────
print("\n  Step 1: Generating source CSV...")
from src.tools.csv_generator.tool import CSVGeneratorTool

csv_tool = CSVGeneratorTool()
csv_result = csv_tool.run({"num_rows": 20, "output_dir": "output"})
if not csv_result.success:
    fail(f"CSV generation failed: {csv_result.error}")
csv_path = csv_result.data.csv_path
ok(f"Source CSV: {csv_path}")

# ── Step 2: Upload to Google Sheets ───────────────────────────────────────────
print("\n  Step 2: Uploading to Google Sheets...")
from src.tools.sheets_tool.tool import SheetsTool

sheets_tool = SheetsTool()
sheets_result = sheets_tool.run({
    "csv_path": csv_path,
    "title": "Employee Data - Integration Test",
})

if not sheets_result.success:
    fail(f"SheetsTool failed: {sheets_result.error}")

ok(f"Upload succeeded in {sheets_result.duration_seconds}s")
ok(f"Spreadsheet URL: {sheets_result.data.spreadsheet_url}")
ok(f"Data rows uploaded: {sheets_result.data.row_count}")

if sheets_result.data.row_count != 20:
    fail(f"Expected 20 data rows, got {sheets_result.data.row_count}")

# ── Step 3: Verify artifact_updates() ─────────────────────────────────────────
updates = sheets_result.data.artifact_updates()
if updates.get("sheet_id") != GOOGLE_SHEET_ID:
    fail(f"artifact_updates() sheet_id wrong: {updates}")
ok(f"artifact_updates() returns correct sheet_id: {GOOGLE_SHEET_ID}")

# ── Step 4: Read back from API to confirm ─────────────────────────────────────
print("\n  Step 4: Reading back from Google Sheets API to confirm...")
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
gc = gspread.Client(auth=creds)
sh = gc.open_by_key(GOOGLE_SHEET_ID)
ws = sh.get_worksheet(0)
all_values = ws.get_all_values()

if len(all_values) == 0:
    fail("Google Sheet returned 0 rows after upload")

data_rows_in_sheet = len(all_values) - 1  # subtract header
if data_rows_in_sheet != 20:
    fail(f"Expected 20 data rows in Sheet, found {data_rows_in_sheet}")
ok(f"Google Sheet contains {data_rows_in_sheet} data rows (confirmed via API readback)")

print(f"\n  CSV_PATH={csv_path}")
print(f"  SHEET_ID={GOOGLE_SHEET_ID}")
print("\n  [INTEGRATION 4 PASSED]")
