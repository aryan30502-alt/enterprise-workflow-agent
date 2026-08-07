"""
ExcelTool — imports CSV data into Microsoft Excel via pywin32 COM automation.

Behaviour:
- Opens a new Excel workbook using win32com.client (COM dispatch).
- Writes all CSV rows into a named worksheet.
- Applies professional header formatting (bold, blue background, white text).
- Auto-fits all columns for readability.
- Saves the workbook as a proper .xlsx file (FileFormat=51).
- Quits Excel cleanly whether the operation succeeds or fails.

Requirements:
- Microsoft Excel must be installed on the system (Windows only).
- pywin32 must be installed (pip install pywin32).

Note on Visible=True: Excel is shown on screen during execution. This is
intentional for the demo video — the reviewer can see Excel physically open,
data populate, and the file save in real time.
"""

import csv
import time
import uuid
from pathlib import Path
from typing import ClassVar, List, Optional, Tuple, Type

from src.core.exceptions import ExcelAutomationError
from src.core.logger import get_logger
from src.models.schemas import ExcelInput, ExcelOutput, ToolResult
from src.tools.base import BaseTool

logger = get_logger(__name__)

# Excel FileFormat constant for .xlsx (xlOpenXMLWorkbook)
_XL_FORMAT_XLSX: int = 51

# Header cell styling (OLE color = R + G*256 + B*65536)
_HEADER_BG_COLOR: int = 68 + (114 << 8) + (196 << 16)   # Office Blue #4472C4
_HEADER_FG_COLOR: int = 255 + (255 << 8) + (255 << 16)   # White #FFFFFF


class ExcelTool(BaseTool[ExcelInput, ExcelOutput]):
    """
    Imports a CSV file into Microsoft Excel using COM automation (pywin32).

    Opens Excel visually, creates a formatted worksheet, saves as .xlsx.
    Guaranteed to release COM resources even if an error occurs mid-operation.
    """

    name: ClassVar[str] = "excel_tool"
    description: ClassVar[str] = (
        "Imports an existing CSV file into Microsoft Excel using pywin32 COM "
        "automation. Opens Excel, creates a new workbook, writes all rows to a "
        "worksheet named 'Employee Data', applies header formatting, auto-fits "
        "columns, and saves the workbook as a .xlsx file. "
        "Requires: csv_path (absolute path to the source CSV). "
        "Call csv_generator first to obtain csv_path."
    )
    input_schema: ClassVar[Type[ExcelInput]] = ExcelInput
    output_schema: ClassVar[Type[ExcelOutput]] = ExcelOutput

    def execute(self, input_data: ExcelInput) -> ToolResult:
        """
        Run the full Excel import workflow via COM automation.

        Returns ToolResult with success=True and ExcelOutput on success.
        Returns ToolResult with success=False if Excel is unavailable or any
        COM error occurs. Always releases COM resources in the finally block.
        Never raises.
        """
        start = time.monotonic()
        excel = None
        wb = None

        try:
            # Lazy import — pywin32 is Windows-only and only needed here.
            import pythoncom
            import win32com.client

            csv_path = Path(input_data.csv_path)
            if not csv_path.exists():
                raise ExcelAutomationError(
                    f"Source CSV not found: {csv_path}. "
                    "Run csv_generator first."
                )

            headers, data_rows = self._read_csv(csv_path)

            output_dir = Path(input_data.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            xlsx_filename = f"employees_{uuid.uuid4().hex[:8]}.xlsx"
            abs_xlsx_path = (output_dir / xlsx_filename).resolve()

            # Initialise COM for this thread.
            pythoncom.CoInitialize()

            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = True          # Show for demo video.
            excel.DisplayAlerts = False   # Suppress overwrite/format dialogs.

            wb = excel.Workbooks.Add()
            ws = wb.ActiveSheet
            ws.Name = "Employee Data"

            self._write_headers(ws, headers)
            self._write_data(ws, data_rows)
            self._format_headers(ws, headers)
            ws.Columns.AutoFit()

            # FileFormat=51 → xlOpenXMLWorkbook (.xlsx)
            wb.SaveAs(Filename=str(abs_xlsx_path), FileFormat=_XL_FORMAT_XLSX)

            duration = round(time.monotonic() - start, 3)
            logger.info(
                "excel_saved",
                path=str(abs_xlsx_path),
                rows=len(data_rows),
                duration_s=duration,
            )

            return ToolResult[ExcelOutput](
                tool_name=self.name,
                success=True,
                data=ExcelOutput(
                    xlsx_path=str(abs_xlsx_path),
                    sheet_name="Employee Data",
                    row_count=len(data_rows),
                ),
                duration_seconds=duration,
            )

        except ExcelAutomationError as exc:
            duration = round(time.monotonic() - start, 3)
            error_msg = str(exc)
            logger.error("excel_automation_failed", error=error_msg)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=error_msg,
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = round(time.monotonic() - start, 3)
            error_msg = f"Excel COM automation error: {exc!r}"
            logger.error("excel_automation_failed", error=error_msg)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=error_msg,
                duration_seconds=duration,
            )
        finally:
            # Always clean up COM objects to avoid orphaned Excel processes.
            if wb is not None:
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass
            if excel is not None:
                try:
                    excel.Quit()
                except Exception:
                    pass
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    # ── Private Helpers ───────────────────────────────────────────────────────

    def _read_csv(self, csv_path: Path) -> Tuple[List[str], List[List[str]]]:
        """Read the CSV and return (headers, data_rows) as lists of strings."""
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            all_rows = list(reader)

        if not all_rows:
            raise ExcelAutomationError(f"CSV file is empty: {csv_path}")

        headers = all_rows[0]
        data_rows = all_rows[1:]
        return headers, data_rows

    def _write_headers(self, ws, headers: List[str]) -> None:
        """Write header row to Excel worksheet (row 1)."""
        for col_idx, header in enumerate(headers, start=1):
            ws.Cells(1, col_idx).Value = header

    def _write_data(self, ws, data_rows: List[List[str]]) -> None:
        """Write all data rows to the worksheet starting at row 2."""
        for row_idx, row in enumerate(data_rows, start=2):
            for col_idx, value in enumerate(row, start=1):
                ws.Cells(row_idx, col_idx).Value = value

    def _format_headers(self, ws, headers: List[str]) -> None:
        """Apply bold text, blue background, and white font to the header row."""
        header_range = ws.Range(
            ws.Cells(1, 1),
            ws.Cells(1, len(headers)),
        )
        header_range.Font.Bold = True
        header_range.Interior.Color = _HEADER_BG_COLOR
        header_range.Font.Color = _HEADER_FG_COLOR
