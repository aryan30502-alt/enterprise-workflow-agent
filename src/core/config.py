from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """
    Application configuration loaded exclusively from environment variables / .env file.
    All fields with no default are REQUIRED and will raise a clear error on startup
    if missing — which is the intended behaviour for a production agent.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # silently ignore unknown env vars
    )

    # ── Gemini LLM (Google AI Studio) ────────────────────────────────────────
    google_api_key: str = Field(
        "",
        description="Google Gemini API key (from Google AI Studio or GCP). Optional if GROQ_API_KEY is set.",
    )
    gemini_model: str = Field(
        "gemini-2.0-flash",
        description="Gemini model identifier.",
    )

    # ── Groq (primary fast-inference backend, free tier) ──────────────────────
    groq_api_key: str = Field(
        "",
        description="Groq API key (gsk_...). When set, used as primary LLM backend.",
    )
    groq_model: str = Field(
        "openai/gpt-oss-120b",
        description="Groq model — fast inference and reliable function calling.",
    )

    # ── OpenRouter (secondary fallback) ───────────────────────────────────────
    openrouter_api_key: str = Field(
        "",
        description="OpenRouter API key (sk-or-v1-...). Used if Groq key not set.",
    )
    openrouter_model: str = Field(
        "google/gemma-4-31b-it:free",
        description="Model name as used on OpenRouter.",
    )
    openrouter_base_url: str = Field(
        "https://openrouter.ai/api/v1",
        description="OpenRouter OpenAI-compatible endpoint.",
    )

    # ── Google Sheets (OAuth Desktop Flow) ───────────────────────────────────
    google_credentials_path: str = Field(
        "credentials/credentials.json",
        description="Path to the OAuth Desktop credentials JSON downloaded from GCP Console.",
    )
    google_token_path: str = Field(
        "credentials/token.json",
        description=(
            "Path where the OAuth token is cached after the first browser login. "
            "Created automatically on first run; reused on all subsequent runs."
        ),
    )
    google_sheet_id: str = Field(
        "",
        description="Target Google Spreadsheet ID. Optional — if empty or inaccessible, the agent auto-creates a new sheet.",
    )

    # ── Agent Behaviour ───────────────────────────────────────────────────────
    max_agent_steps: int = Field(
        15,
        description="Maximum number of LangGraph loop iterations (safety ceiling).",
    )
    max_tool_retries: int = Field(
        2,
        description="Maximum agent-level retries per failing tool.",
    )
    output_dir: str = Field(
        "output",
        description="Directory where CSV and XLSX files will be saved.",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(
        "INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    log_format: str = Field(
        "console",
        description="Structlog output format: 'console' (human-readable) or 'json'.",
    )


# Singleton instantiated at import time.
# A missing required field raises pydantic.ValidationError with a clear message.
config = AppConfig()
