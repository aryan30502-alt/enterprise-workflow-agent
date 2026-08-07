"""
Dual logging system:
  1. structlog  — JSON or readable console logs written to stdout and to
                  output/logs/{task_id}.jsonl for audit purposes.
  2. Rich       — Live terminal UI panel updated in real time during execution.

Both systems are initialised once and shared via module-level singletons.
"""

import logging
import os
import sys
from typing import Optional

import structlog
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


# ── Singleton Rich console ────────────────────────────────────────────────────

_console = Console()


def get_rich_console() -> Console:
    """Return the singleton Rich console. Use this everywhere instead of print()."""
    return _console


# ── structlog setup ───────────────────────────────────────────────────────────

def setup_logging(log_level: str = "INFO", log_format: str = "console") -> None:
    """
    Configure structlog with the chosen format.

    Call this ONCE at application startup in main.py before any logger is used.

    Args:
        log_level:  Standard Python logging level string (DEBUG, INFO, etc.).
        log_format: "console" for development, "json" for production/CI.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format.lower() == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger. Use one per module."""
    return structlog.get_logger(name)


# ── Rich Live Progress Panel ──────────────────────────────────────────────────

class AgentProgressPanel:
    """
    Manages a Rich Live display that renders a real-time execution table and
    a planner reasoning panel during agent execution.

    Usage:
        panel = AgentProgressPanel()
        panel.start(prompt="Create employee CSV...")
        panel.update_reasoning("CSV was generated. Selecting excel_tool next.")
        panel.update_step("csv_generator", status="✅ Success", duration="0.31s")
        panel.stop()
    """

    # Status display strings (called from nodes after tool execution)
    STATUS_RUNNING = "[bold yellow]>> Running[/bold yellow]"
    STATUS_SUCCESS = "[bold green]OK Success[/bold green]"
    STATUS_FAILED  = "[bold red]!! Failed[/bold red]"
    STATUS_RETRIED = "[bold orange1]~~ Retried[/bold orange1]"

    def __init__(self) -> None:
        self._console = get_rich_console()
        self._table = self._build_table()
        self._reasoning: str = "[dim]Waiting for planner...[/dim]"
        self._live: Optional[Live] = None
        self._step_index: int = 0

    def _build_table(self) -> Table:
        table = Table(
            title="[bold magenta]AUTONOMOUS AGENT EXECUTION[/bold magenta]",
            show_header=True,
            header_style="bold cyan",
            border_style="bright_black",
            expand=True,
        )
        table.add_column("Step",     justify="center", width=6)
        table.add_column("Tool",     style="cyan",     min_width=20)
        table.add_column("Status",   min_width=16)
        table.add_column("Duration", justify="right",  width=10)
        return table

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._table, name="table"),
            Layout(
                Panel(
                    Text.from_markup(self._reasoning),
                    title="[bold green]Planner Reasoning[/bold green]",
                    border_style="green",
                    padding=(0, 1),
                ),
                name="reasoning",
                size=4,
            ),
        )
        return layout

    def start(self, prompt: str) -> None:
        """Start the live display. Call once at the beginning of a run."""
        self._console.print(
            Panel(
                f"[bold white]{prompt}[/bold white]",
                title="[bold blue]Prompt[/bold blue]",
                border_style="blue",
            )
        )
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=6,
            transient=False,
        )
        self._live.start()

    def update_reasoning(self, text: str) -> None:
        """Update the planner reasoning panel with the LLM's latest thought."""
        self._reasoning = text
        if self._live:
            self._live.update(self._render())

    def update_step(
        self,
        tool_name: str,
        status: str,
        duration: str = "—",
    ) -> None:
        """
        Add a completed step row to the execution table.

        Args:
            tool_name: Name of the tool that was executed.
            status:    One of the STATUS_* class constants.
            duration:  Formatted duration string (e.g., "1.23s").
        """
        self._step_index += 1
        self._table.add_row(
            str(self._step_index),
            tool_name,
            status,
            duration,
        )
        if self._live:
            self._live.update(self._render())

    def stop(self) -> None:
        """Stop and finalise the live display."""
        if self._live:
            self._live.stop()
            self._live = None
