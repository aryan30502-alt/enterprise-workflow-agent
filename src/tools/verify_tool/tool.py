"""
VerifyTool — cross-validates row counts across all three data targets.

Reads the source CSV, the Excel workbook, and the Google Sheet independently
and compares row counts. A mismatch is reported in the output but does NOT
cause the tool itself to fail — the tool ran successfully, it just detected
a discrepancy. The agent graph uses data.all_match to decide next steps.

This tool has no side effects. It is purely a reader/comparator.
"""

import csv
import time
from pathlib import Path
from typing import ClassVar, List, Type

import openpyxl

from src.core.auth import get_google_credentials
from src.core.exceptions import VerificationError
from src.core.logger import get_logger
from src.models.schemas import ToolResult, VerifyInput, VerifyOutput
from src.tools.base import BaseTool

logger = get_logger(__name__)


class VerifyTool(BaseTool[VerifyInput, VerifyOutput]):
    """
    Verifies data integrity across the CSV, Excel, and Google Sheets targets.

    Counts data rows (excluding header) in each target and checks that all
    three counts are identical. Returns a structured result indicating whether
    verification passed or failed, including the individual counts and a
    human-readable summary.
    """

    name: ClassVar[str] = "verify_tool"
    description: ClassVar[str] = (
        "Verifies that the row counts match across the CSV file, the Excel "
        "workbook, and the Google Spreadsheet. Reads each target independently "
        "and compares data row counts (excluding the header row). Returns "
        "csv_rows, xlsx_rows, sheet_rows, all_match (bool), and a summary string. "
        "Call this AFTER csv_generator, excel_tool, and sheets_tool have all "
        "succeeded. Requires: csv_path, xlsx_path, sheet_id."
    )
    input_schema: ClassVar[Type[VerifyInput]] = VerifyInput
    output_schema: ClassVar[Type[VerifyOutput]] = VerifyOutput

    def execute(self, input_data: VerifyInput) -> ToolResult:
        """
        Count rows in all three targets and compare.

        NOTE: success=True means the verification tool ran successfully.
              Check data.all_match to know whether row counts agree.

        Returns ToolResult with success=True always if reads succeed.
        Returns ToolResult with success=False only if a target cannot be read.
        Never raises.
        """
        start = time.monotonic()

        try:
            csv_rows = self._count_csv_rows(input_data.csv_path)
            xlsx_rows = self._count_xlsx_rows(input_data.xlsx_path)
            sheet_rows = self._count_sheet_rows(input_data.sheet_id)

            all_match = (csv_rows == xlsx_rows == sheet_rows)

            if all_match:
                summary = (
                    f"Verification PASSED - all targets contain "
                    f"{csv_rows} data rows."
                )
            else:
                summary = (
                    f"Verification FAILED - row count mismatch: "
                    f"CSV={csv_rows}, Excel={xlsx_rows}, "
                    f"Google Sheets={sheet_rows}."
                )

            duration = round(time.monotonic() - start, 3)

            logger.info(
                "verification_complete",
                csv_rows=csv_rows,
                xlsx_rows=xlsx_rows,
                sheet_rows=sheet_rows,
                all_match=all_match,
                duration_s=duration,
            )

            return ToolResult[VerifyOutput](
                tool_name=self.name,
                success=True,
                data=VerifyOutput(
                    csv_rows=csv_rows,
                    xlsx_rows=xlsx_rows,
                    sheet_rows=sheet_rows,
                    all_match=all_match,
                    summary=summary,
                ),
                duration_seconds=duration,
            )

        except VerificationError as exc:
            duration = round(time.monotonic() - start, 3)
            error_msg = str(exc)
            logger.error("verification_failed", error=error_msg)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=error_msg,
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = round(time.monotonic() - start, 3)
            error_msg = f"Verification tool failed unexpectedly: {exc!r}"
            logger.error("verification_failed", error=error_msg)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=error_msg,
                duration_seconds=duration,
            )

    # ── Private Readers ───────────────────────────────────────────────────────

    def _count_csv_rows(self, csv_path: str) -> int:
        """Count data rows in the CSV (total rows minus 1 header row)."""
        path = Path(csv_path)
        if not path.exists():
            raise VerificationError(
                f"CSV file not found for verification: {csv_path}"
            )
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            total = sum(1 for _ in reader)
        if total == 0:
            raise VerificationError(f"CSV file is empty: {csv_path}")
        return total - 1  # Subtract header row.

    def _count_xlsx_rows(self, xlsx_path: str) -> int:
        """
        Count data rows in the Excel workbook (max_row of active sheet minus header).

        Uses openpyxl in read-only mode for performance.
        """
        path = Path(xlsx_path)
        if not path.exists():
            raise VerificationError(
                f"Excel workbook not found for verification: {xlsx_path}"
            )
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.active
            max_row = ws.max_row
        finally:
            wb.close()

        if max_row is None or max_row < 1:
            raise VerificationError(
                f"Excel workbook appears empty: {xlsx_path}"
            )
        return max_row - 1  # Subtract header row.

    def _count_sheet_rows(self, sheet_id: str) -> int:
        """
        Count data rows in the Google Sheet using the Sheets API v4 directly.

        Uses googleapiclient (not gspread) to avoid the AuthorizedSession
        permission conflicts. Returns total non-empty rows minus the header.
        """
        try:
            from googleapiclient.discovery import build
            from google.auth.transport.requests import Request

            creds = get_google_credentials()
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())

            sheets_svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
            result = (
                sheets_svc.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range="A:Z")
                .execute()
            )
            values = result.get("values", [])
        except Exception as exc:
            raise VerificationError(
                f"Failed to read Google Sheet '{sheet_id}': {exc}"
            ) from exc

        if not values:
            raise VerificationError(
                f"Google Sheet '{sheet_id}' returned no data."
            )
        return len(values) - 1  # Subtract header row.
