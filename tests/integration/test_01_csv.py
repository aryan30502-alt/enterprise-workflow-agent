"""
Integration Test 1: CSVGeneratorTool — real Faker data, real filesystem write.

Zero external dependencies (no API keys, no Excel, no network).
Verifies:
  - Tool produces a valid CSV at a real path
  - Row count matches requested num_rows
  - All 7 expected columns present
  - Data rows are unique (no duplicate emails)
  - Downstream tools can read the file
  - artifact_updates() returns the correct csv_path
"""

import os
import sys
import csv

sys.path.insert(0, ".")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet-id")


def ok(msg):  print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}"); sys.exit(1)
def section(t): print(f"\n{'='*55}\n  {t}\n{'='*55}")


section("INTEGRATION 1: CSVGeneratorTool (real filesystem)")

from src.tools.csv_generator.tool import CSVGeneratorTool
from src.models.schemas import CSVGeneratorInput

tool = CSVGeneratorTool()

# ── Run with real filesystem ──────────────────────────────────────────────────
result = tool.run({"num_rows": 25, "output_dir": "output"})

if not result.success:
    fail(f"Tool returned success=False: {result.error}")

ok(f"Tool succeeded in {result.duration_seconds}s")

csv_path = result.data.csv_path
ok(f"CSV path returned: {csv_path}")

import pathlib
p = pathlib.Path(csv_path)
if not p.exists():
    fail(f"CSV file does not exist at: {csv_path}")
ok("CSV file exists on disk")

# ── Read and validate the file ────────────────────────────────────────────────
with open(csv_path, "r", encoding="utf-8") as fh:
    reader = csv.DictReader(fh)
    rows = list(reader)

EXPECTED_COLS = {"id", "full_name", "email", "department", "salary", "hire_date", "phone"}
actual_cols = set(rows[0].keys()) if rows else set()
if actual_cols != EXPECTED_COLS:
    fail(f"Unexpected columns. Got {actual_cols}, expected {EXPECTED_COLS}")
ok(f"All 7 columns present: {sorted(actual_cols)}")

if len(rows) != 25:
    fail(f"Expected 25 rows, got {len(rows)}")
ok(f"Row count correct: {len(rows)}")

emails = [r["email"] for r in rows]
if len(emails) != len(set(emails)):
    fail(f"Duplicate emails found — Faker uniqueness broke")
ok("All emails unique")

# ── artifact_updates() contract ───────────────────────────────────────────────
updates = result.data.artifact_updates()
if updates.get("csv_path") != csv_path:
    fail(f"artifact_updates() csv_path mismatch: {updates}")
ok(f"artifact_updates() returns correct csv_path")

# Expose path for downstream integration tests
print(f"\n  CSV_PATH={csv_path}")
print("\n  [INTEGRATION 1 PASSED]")
