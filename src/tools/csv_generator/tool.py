"""
CSVGeneratorTool — generates a realistic employee CSV using the Faker library.

Produces deterministically-structured, uniquely-seeded synthetic employee data.
Saves the CSV to a timestamped file in the configured output directory.
"""

import csv
import time
import uuid
from pathlib import Path
from typing import ClassVar, List, Type

from faker import Faker

from src.core.exceptions import CSVGenerationError
from src.core.logger import get_logger
from src.models.schemas import CSVGeneratorInput, CSVGeneratorOutput, ToolResult
from src.tools.base import BaseTool

logger = get_logger(__name__)

# Single Faker instance — thread-safe for single-threaded use.
_faker = Faker()

# Column order is fixed and authoritative. All downstream tools rely on this.
COLUMNS: List[str] = [
    "id",
    "full_name",
    "email",
    "department",
    "salary",
    "hire_date",
    "phone",
]

DEPARTMENTS: List[str] = [
    "Engineering",
    "Marketing",
    "Finance",
    "Human Resources",
    "Sales",
    "Operations",
    "Legal",
    "Product",
    "Data Science",
    "Customer Success",
]


class CSVGeneratorTool(BaseTool[CSVGeneratorInput, CSVGeneratorOutput]):
    """
    Generates a CSV file containing synthetic employee records.

    Each record contains: id, full_name, email, department, salary,
    hire_date, and phone. Uses Faker for realistic, non-repeating data.
    """

    name: ClassVar[str] = "csv_generator"
    description: ClassVar[str] = (
        "Generates a CSV file containing realistic synthetic employee records "
        "using the Faker library. Each record has: id, full_name, email, "
        "department, salary (USD), hire_date (ISO-8601), and phone. "
        "Returns the absolute path to the saved CSV and the exact row count. "
        "Call this tool first before excel_tool or sheets_tool."
    )
    input_schema: ClassVar[Type[CSVGeneratorInput]] = CSVGeneratorInput
    output_schema: ClassVar[Type[CSVGeneratorOutput]] = CSVGeneratorOutput

    def execute(self, input_data: CSVGeneratorInput) -> ToolResult:
        """
        Generate employee CSV and save it to disk.

        Returns ToolResult with success=True and CSVGeneratorOutput on success.
        Returns ToolResult with success=False on any filesystem or Faker error.
        Never raises.
        """
        start = time.monotonic()

        try:
            output_path = Path(input_data.output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Use UUID suffix to make each run's file unique and traceable.
            csv_filename = f"employees_{uuid.uuid4().hex[:8]}.csv"
            csv_path = output_path / csv_filename

            rows = self._generate_rows(input_data.num_rows)

            with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)

            abs_csv_path = str(csv_path.resolve())
            duration = round(time.monotonic() - start, 3)

            logger.info(
                "csv_generated",
                path=abs_csv_path,
                rows=len(rows),
                duration_s=duration,
            )

            return ToolResult[CSVGeneratorOutput](
                tool_name=self.name,
                success=True,
                data=CSVGeneratorOutput(
                    csv_path=abs_csv_path,
                    row_count=len(rows),
                    columns=COLUMNS,
                ),
                duration_seconds=duration,
            )

        except OSError as exc:
            duration = round(time.monotonic() - start, 3)
            error_msg = f"Filesystem error while writing CSV: {exc}"
            logger.error("csv_generation_failed", error=error_msg)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=error_msg,
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = round(time.monotonic() - start, 3)
            error_msg = f"CSV generation failed: {exc!r}"
            logger.error("csv_generation_failed", error=error_msg)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=error_msg,
                duration_seconds=duration,
            )

    def _generate_rows(self, count: int) -> List[dict]:
        """
        Generate `count` employee record dicts using Faker.

        Uses Faker().unique to guarantee non-repeating emails within a run.
        """
        _faker.unique.clear()  # Reset uniqueness tracker for this run.
        rows = []
        for i in range(1, count + 1):
            rows.append(
                {
                    "id": i,
                    "full_name": _faker.name(),
                    "email": _faker.unique.email(),
                    "department": _faker.random_element(DEPARTMENTS),
                    "salary": _faker.random_int(min=40_000, max=150_000, step=500),
                    "hire_date": _faker.date_between(
                        start_date="-10y", end_date="today"
                    ).isoformat(),
                    "phone": _faker.phone_number(),
                }
            )
        return rows
