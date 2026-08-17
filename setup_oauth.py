"""
setup_oauth.py — One-time Google OAuth setup.

Run this ONCE in your terminal:
    python setup_oauth.py

IMPORTANT on the Google consent screen:
  - Click the ACCOUNT you want to use
  - If you see "Google hasn't verified this app" -> click "Advanced" -> "Go to ... (unsafe)"
  - Click ALLOW (not Cancel or Back)

After this script finishes, run:
    python main.py
"""

import sys
import os
import pathlib

os.chdir(pathlib.Path(__file__).parent)
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from src.core.config import config

CREDS = pathlib.Path(config.google_credentials_path)
TOKEN = pathlib.Path(config.google_token_path)

print("=" * 60)
print("  Google OAuth Setup")
print("=" * 60)

if not CREDS.exists():
    print(f"\nERROR: {CREDS} not found.")
    sys.exit(1)

if TOKEN.exists():
    print(f"\ntoken.json already exists at: {TOKEN}")
    ans = input("Re-authenticate? [y/N]: ").strip().lower()
    if ans != "y":
        print("Using existing token. Run: python main.py")
        sys.exit(0)
    TOKEN.unlink()

print()
print("IMPORTANT: When the browser opens:")
print("  1. Select your Google account")
print("  2. If you see 'App not verified' -> click Advanced -> Go to app (unsafe)")
print("  3. Click ALLOW  (not Cancel or Back)")
print()
print("Opening browser...")
print()

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

flow = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES)

try:
    creds = flow.run_local_server(
        port=0,
        open_browser=True,
        success_message=(
            "Authentication complete! You may close this tab and return to the terminal."
        ),
        authorization_prompt_message=(
            "Visit this URL in your browser to authorize:\n{url}\n"
        ),
    )
except Exception as exc:
    err = str(exc)
    if "access_denied" in err or "Access denied" in err.lower():
        print()
        print("ERROR: You clicked Cancel or denied access on the Google consent screen.")
        print()
        print("Please run this script again and this time:")
        print("  - Click ALLOW on the Google consent screen")
        print("  - If you see 'App not verified', click Advanced -> Go to ... (unsafe) -> Allow")
        print()
    else:
        print(f"\nOAuth error: {exc}\n")
    sys.exit(1)

TOKEN.parent.mkdir(parents=True, exist_ok=True)
TOKEN.write_text(creds.to_json(), encoding="utf-8")

print()
print(f"Saved: {TOKEN}")
print()
print("Setup complete! Now run:")
print("    python main.py")
print()
