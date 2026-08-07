"""
End-to-End Integration Runner

Runs every integration test in order and reports results.
Automatically skips tests requiring credentials if they are not present.
Runs the M4 graph simulations as a regression guard at the end.

Usage:
  python tests/integration/run_all.py
"""

import os
import sys
import subprocess
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))


def run_test(label: str, script: str) -> bool:
    """Run a test script as a subprocess and return True if it passed."""
    print(f"\n{'-'*60}")
    print(f"  Running: {label}")
    print(f"{'-'*60}")

    result = subprocess.run(
        [sys.executable, script],
        cwd=str(pathlib.Path(__file__).parent.parent.parent),
        capture_output=False,
    )

    code = result.returncode
    if code == 0:
        print(f"\n  [RESULT] {label}: PASSED (exit 0)")
        return True
    else:
        print(f"\n  [RESULT] {label}: FAILED (exit {code})")
        return False


TESTS = [
    ("Integration 1: CSV Generator",     "tests/integration/test_01_csv.py"),
    ("Integration 2: Excel (pywin32)",   "tests/integration/test_02_excel.py"),
    ("Integration 3: Gemini Planner",    "tests/integration/test_03_gemini_planner.py"),
    ("Integration 4: Google Sheets",     "tests/integration/test_04_sheets.py"),
    ("Integration 5: Cross-Verify",      "tests/integration/test_05_verify.py"),
    ("Regression: M4 Graph Simulations", "verify_m4.py"),
]

print("\n" + "=" * 60)
print("  END-TO-END INTEGRATION SUITE")
print("=" * 60)

results = {}
for label, script in TESTS:
    passed = run_test(label, script)
    results[label] = passed

print("\n" + "=" * 60)
print("  FINAL INTEGRATION REPORT")
print("=" * 60)
print()

all_passed = True
for label, passed in results.items():
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {label}")
    if not passed:
        all_passed = False

print()
if all_passed:
    print("  ALL TESTS PASSED — system is production-ready.")
else:
    print("  ONE OR MORE TESTS FAILED — do not proceed to demo.")

print()
sys.exit(0 if all_passed else 1)
