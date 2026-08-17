"""
src/core/auth.py — OAuth Desktop Flow authentication helper.

First run:
  1. Reads credentials.json (OAuth Desktop App client secrets).
  2. Prints the authorization URL to the terminal.
  3. Waits for the user to open the URL in a browser and grant access.
  4. Captures the redirect on localhost:8080 and saves token.json.

Subsequent runs:
  1. Loads token.json from disk.
  2. Refreshes silently if expired.
  3. Returns valid Credentials — no browser interaction required.
"""

from __future__ import annotations

import pathlib
import sys
from typing import List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.core.config import config
from src.core.logger import get_logger

logger = get_logger(__name__)

_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Fixed port so we can pre-compute the redirect URI and print the URL before blocking.
_OAUTH_PORT: int = 8080


def get_google_credentials() -> Credentials:
    """
    Return valid Google OAuth2 Credentials.

    If a cached token exists at config.google_token_path and is valid (or can
    be silently refreshed), it is returned immediately with no user interaction.

    On first run (no token.json), this function:
      1. Prints the OAuth authorization URL to stdout.
      2. Starts a local HTTP server on port 8080.
      3. Waits for the user to open the URL in a browser and grant access.
      4. Captures the authorization code via the localhost redirect.
      5. Saves token.json for all future runs.

    Returns:
        google.oauth2.credentials.Credentials ready for use with gspread.

    Raises:
        FileNotFoundError: If credentials.json is missing.
        RuntimeError: If the OAuth flow fails.
    """
    creds_path = pathlib.Path(config.google_credentials_path)
    token_path = pathlib.Path(config.google_token_path)

    if not creds_path.exists():
        raise FileNotFoundError(
            f"OAuth credentials file not found: {creds_path}\n"
            "Download OAuth Desktop credentials from GCP Console -> APIs & Services "
            "-> Credentials and place the JSON at the configured path."
        )

    creds: Credentials | None = None

    # ── 1. Try loading cached token ────────────────────────────────────────────
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
            logger.info("oauth_token_loaded", path=str(token_path))
        except Exception as exc:
            logger.warning("oauth_token_load_failed", path=str(token_path), error=str(exc))
            creds = None

    # ── 2. Silent refresh if expired ──────────────────────────────────────────
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("oauth_token_refreshed")
            _save_token(creds, token_path)
            return creds
        except Exception as exc:
            logger.warning("oauth_token_refresh_failed", error=str(exc))
            creds = None

    # ── 3. Already valid — return immediately ─────────────────────────────────
    if creds and creds.valid:
        return creds

    # ── 4. Full browser flow ──────────────────────────────────────────────────
    creds = _run_oauth_flow(creds_path)
    _save_token(creds, token_path)
    return creds


def _run_oauth_flow(creds_path: pathlib.Path) -> Credentials:
    """
    Run the OAuth Desktop flow with an explicit URL printed to stdout.

    Uses a fixed redirect URI (http://localhost:8080/) so the authorization
    URL can be computed and printed BEFORE the blocking local server starts.
    The user opens the URL in any browser; the redirect completes automatically.
    """
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), _SCOPES)

    # Pre-set redirect_uri to match the fixed port so auth_url is correct.
    flow.redirect_uri = f"http://localhost:{_OAUTH_PORT}/"

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",          # Force consent screen to ensure refresh_token is issued.
    )

    # Print the URL as prominently as possible before the server blocks.
    _print_auth_url(auth_url)
    logger.info("oauth_auth_url", url=auth_url, port=_OAUTH_PORT)

    try:
        creds = flow.run_local_server(
            port=_OAUTH_PORT,
            open_browser=False,              # Do not attempt browser auto-open.
            authorization_prompt_message="", # We already printed the URL above.
            success_message=(
                "Authentication successful! You may close this browser tab "
                "and return to the terminal."
            ),
        )
    except OSError:
        # Fallback to any free port if 8080 is busy
        creds = flow.run_local_server(
            port=0,
            open_browser=True,
            success_message=(
                "Authentication successful! You may close this browser tab "
                "and return to the terminal."
            ),
        )

    logger.info("oauth_flow_complete")
    return creds


def _print_auth_url(url: str) -> None:
    """Write the authorization URL to stdout with clear formatting."""
    border = "=" * 70
    lines = [
        "",
        border,
        "  GOOGLE OAUTH - ACTION REQUIRED",
        border,
        "",
        "  Open this URL in your browser to grant Google Sheets access:",
        "",
        f"  {url}",
        "",
        f"  Waiting for you to complete login on http://localhost:{_OAUTH_PORT}/",
        border,
        "",
    ]
    for line in lines:
        sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _save_token(creds: Credentials, token_path: pathlib.Path) -> None:
    """Persist token to disk so subsequent runs skip the browser flow."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    logger.info("oauth_token_saved", path=str(token_path))
