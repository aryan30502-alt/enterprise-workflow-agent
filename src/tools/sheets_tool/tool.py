"""
SheetsTool — uploads CSV data to Google Sheets using the Sheets API v4 directly.

Bypasses gspread for writes to avoid permission conflicts. Strategy:
1. Try to write to the configured spreadsheet (GOOGLE_SHEET_ID in .env).
2. If 403 (OAuth user doesn't own that sheet), auto-create a NEW spreadsheet.
3. Upload all CSV rows in a single values.update call.
4. Return the spreadsheet URL, ID, and exact row count.
"""

import csv
import time
from pathlib import Path
from typing import ClassVar, List, Type

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.core.auth import get_google_credentials
from src.core.exceptions import GoogleSheetsAPIError
from src.core.logger import get_logger
from src.models.schemas import SheetsInput, SheetsOutput, ToolResult
from src.tools.base import BaseTool

logger = get_logger(__name__)


class SheetsTool(BaseTool[SheetsInput, SheetsOutput]):
    """
    Uploads employee CSV data to Google Sheets.

    Uses the Sheets API v4 via googleapiclient for all operations, which avoids
    the gspread permission quirks. If the configured spreadsheet is not writable
    by the OAuth account, a new one is created automatically.
    """

    name: ClassVar[str] = "sheets_tool"
    description: ClassVar[str] = (
        "Uploads the contents of a CSV file to a Google Spreadsheet. "
        "Tries the configured GOOGLE_SHEET_ID first; if write access is denied, "
        "creates a new spreadsheet automatically and uses that instead. "
        "Returns the spreadsheet URL and the number of data rows uploaded. "
        "Requires: csv_path (absolute path to the source CSV). "
        "Call csv_generator first to obtain csv_path."
    )
    input_schema: ClassVar[Type[SheetsInput]] = SheetsInput
    output_schema: ClassVar[Type[SheetsOutput]] = SheetsOutput

    def execute(self, input_data: SheetsInput) -> ToolResult:
        """Upload CSV data to Google Sheets. Never raises."""
        start = time.monotonic()

        try:
            csv_path = Path(input_data.csv_path)
            if not csv_path.exists():
                raise GoogleSheetsAPIError(
                    f"Source CSV not found: {csv_path}. Run csv_generator first."
                )

            all_rows = self._read_csv(csv_path)
            if not all_rows:
                raise GoogleSheetsAPIError(f"CSV file is empty: {csv_path}")

            # Fresh credentials — refresh if needed.
            creds = get_google_credentials()
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                logger.info("oauth_token_refreshed")

            sheets_svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

            # Determine target spreadsheet (use existing or create new).
            sheet_id = self._resolve_spreadsheet(sheets_svc, input_data.title)

            # Upload data.
            self._clear_and_upload(sheets_svc, sheet_id, all_rows, input_data.title)

            spreadsheet_url = (
                f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
            )
            data_row_count = len(all_rows) - 1  # Exclude header.
            duration = round(time.monotonic() - start, 3)

            logger.info(
                "sheets_uploaded",
                sheet_id=sheet_id,
                rows=data_row_count,
                duration_s=duration,
            )

            return ToolResult[SheetsOutput](
                tool_name=self.name,
                success=True,
                data=SheetsOutput(
                    spreadsheet_id=sheet_id,
                    spreadsheet_url=spreadsheet_url,
                    row_count=data_row_count,
                ),
                duration_seconds=duration,
            )

        except GoogleSheetsAPIError as exc:
            duration = round(time.monotonic() - start, 3)
            error_msg = str(exc)
            logger.error("sheets_upload_failed", error=error_msg)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=error_msg,
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = round(time.monotonic() - start, 3)
            error_msg = f"Sheets tool failed unexpectedly: {exc!r}"
            logger.error("sheets_upload_failed", error=error_msg)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=error_msg,
                duration_seconds=duration,
            )

    # ── Private Helpers ───────────────────────────────────────────────────────

    def _resolve_spreadsheet(self, sheets_svc, title: str) -> str:
        """Always create a fresh spreadsheet owned by the OAuth account."""
        return self._create_spreadsheet(sheets_svc, title)

    def _create_spreadsheet(self, sheets_svc, title: str) -> str:
        """Create a new Google Spreadsheet owned by the OAuth account."""
        try:
            result = (
                sheets_svc.spreadsheets()
                .create(
                    body={"properties": {"title": title}},
                    fields="spreadsheetId",
                )
                .execute()
            )
            new_id = result["spreadsheetId"]
            logger.info("sheets_created_new", sheet_id=new_id, title=title)
            return new_id
        except HttpError as exc:
            raise GoogleSheetsAPIError(
                f"Failed to create new spreadsheet: {exc}"
            ) from exc

    def _clear_and_upload(
        self,
        sheets_svc,
        sheet_id: str,
        all_rows: List[List[str]],
        title: str,
    ) -> None:
        """Clear the sheet, optionally rename tab, then bulk-upload rows."""
        # Full clear.
        sheets_svc.spreadsheets().values().clear(
            spreadsheetId=sheet_id, range="A:Z"
        ).execute()

        # Rename the first tab (cosmetic — ignore errors).
        try:
            meta = sheets_svc.spreadsheets().get(
                spreadsheetId=sheet_id, fields="sheets.properties"
            ).execute()
            first_sheet_id = meta["sheets"][0]["properties"]["sheetId"]
            sheets_svc.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={
                    "requests": [
                        {
                            "updateSheetProperties": {
                                "properties": {
                                    "sheetId": first_sheet_id,
                                    "title": title,
                                },
                                "fields": "title",
                            }
                        }
                    ]
                },
            ).execute()
        except Exception:
            pass  # Rename is cosmetic — don't fail on error.

        # Upload all rows (header + data) in a single request.
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="A1",
            valueInputOption="RAW",
            body={"values": all_rows},
        ).execute()

    def _read_csv(self, csv_path: Path) -> List[List[str]]:
        """Read CSV and return all rows (including header) as List[List[str]]."""
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            return list(reader)
