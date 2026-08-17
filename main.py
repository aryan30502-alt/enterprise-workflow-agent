"""
main.py — Production entry point for the autonomous agent.

Usage:
  python main.py
  python main.py "Generate 30 employee records, import to Excel, upload to Sheets, verify."

The prompt is optional. If omitted, the default production prompt is used.
"""

import sys
import os

# Force UTF-8 on Windows console so Rich output never crashes with cp1252.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console

console = Console()


def main() -> None:
    # Load environment variables FIRST — before any src import touches config.
    from dotenv import load_dotenv
    load_dotenv()

    prompt = (
        " ".join(sys.argv[1:]).strip()
        or (
            "Generate a CSV file with 20 realistic employee records, "
            "import it into Microsoft Excel with professional formatting, "
            "upload it to Google Sheets, then verify that all three targets "
            "contain exactly the same number of data rows."
        )
    )

    console.rule("[bold blue]Autonomous Agent - Starting")
    console.print(f"[dim]Prompt:[/dim] {prompt}\n")

    # Validate prerequisites — will sys.exit(1) with a clear message if broken.
    _check_prerequisites()

    # Trigger OAuth browser flow BEFORE the graph starts so there is no
    # mid-graph interactive pause. Token is cached to credentials/token.json.
    _ensure_google_auth()

    from src.agent.graph import build_graph, create_initial_state
    from src.agent.nodes import llm_planner
    from src.core.logger import AgentProgressPanel, setup_logging
    from src.core.config import config
    from src.tools import registry
    from src.models.schemas import AgentStatus

    setup_logging(log_level=config.log_level, log_format=config.log_format)

    # Only use the Rich live panel when running in a real interactive terminal.
    # In background tasks or CI, panel=None gives clean text output.
    panel = None
    if sys.stdout.isatty():
        panel = AgentProgressPanel()
        panel.start(prompt=prompt)

    graph = build_graph(
        planner_fn=llm_planner,
        tool_registry=registry,
        panel=panel,
    )

    initial = create_initial_state(prompt)
    console.print(f"[dim]Task ID:[/dim] {initial['task_id']}\n")

    try:
        final = graph.invoke(initial)
    except KeyboardInterrupt:
        panel.stop()
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        sys.exit(130)
    except Exception as exc:
        panel.stop()
        console.print(f"\n[bold red]Fatal error:[/bold red] {exc!r}")
        sys.exit(1)

    # ── Final summary ──────────────────────────────────────────────────────────
    status = final["status"]
    color = "green" if status == AgentStatus.COMPLETED else "red"
    console.rule(f"[bold {color}]Agent {status.value.upper()}")

    console.print(f"[bold]Steps completed:[/bold] {len(final['step_reports'])}")
    for step in final["step_reports"]:
        icon = "[green]OK[/green]" if step.status.value == "success" else "[red]FAIL[/red]"
        console.print(
            f"  {icon} Step {step.step_number}: {step.tool_name} "
            f"[dim]({step.duration_seconds}s)[/dim]"
        )

    if final.get("csv_path"):
        console.print(f"\n[bold]CSV:[/bold]  {final['csv_path']}")
    if final.get("xlsx_path"):
        console.print(f"[bold]XLSX:[/bold] {final['xlsx_path']}")
    if final.get("sheet_id"):
        console.print(
            f"[bold]Sheet:[/bold] https://docs.google.com/spreadsheets/d/"
            f"{final['sheet_id']}/edit"
        )
    if final.get("verification_passed") is True:
        console.print("\n[bold green]Verification PASSED - all targets match.[/bold green]")
    elif final.get("verification_passed") is False:
        console.print("\n[bold red]Verification FAILED - row count mismatch.[/bold red]")

    if final["error_log"]:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in final["error_log"]:
            console.print(f"  [red]- {err}[/red]")

    sys.exit(0 if status == AgentStatus.COMPLETED else 1)


def _check_prerequisites() -> None:
    """
    Validate required configuration before making any external calls.
    Exits with a clear error message if anything is missing.
    """
    import pathlib
    from src.core.config import config

    errors = []

    has_llm_key = bool(
        config.groq_api_key
        or config.google_api_key
        or config.openrouter_api_key
    )
    if not has_llm_key:
        errors.append(
            "No LLM API key configured. Set GROQ_API_KEY (recommended), "
            "GOOGLE_API_KEY, or OPENROUTER_API_KEY in .env"
        )

    creds_path = pathlib.Path(config.google_credentials_path)
    token_path = pathlib.Path(config.google_token_path)
    if not creds_path.exists() and not token_path.exists():
        errors.append(
            f"OAuth credentials file not found at: {creds_path}. "
            "Download OAuth Desktop credentials from GCP Console and place the JSON there."
        )

    if errors:
        console.print("\n[bold red]CONFIGURATION ERRORS - cannot start:[/bold red]")
        for i, err in enumerate(errors, 1):
            console.print(f"  {i}. {err}")
        console.print(
            "\nSee [bold].env.example[/bold] for the full configuration reference.\n"
        )
        sys.exit(1)


def _ensure_google_auth() -> None:
    """
    Run the OAuth flow BEFORE graph invocation so the browser prompt (if any)
    happens at startup — not mid-graph inside a tool call.

    If token.json already exists and is valid, this returns instantly with no
    browser interaction. On first run, the browser opens and token.json is saved.
    """
    console.print("[dim]Checking Google OAuth credentials...[/dim]")
    try:
        from src.core.auth import get_google_credentials
        creds = get_google_credentials()
        console.print("[dim]Google OAuth: authenticated.[/dim]\n")
    except Exception as exc:
        console.print(f"\n[bold red]Google OAuth failed:[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
