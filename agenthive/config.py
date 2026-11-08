"""AgentHive Configuration Module.
Loads environment variables and configuration settings.
"""

from pathlib import Path
from typing import Optional
import os
import shutil
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

def _effective_host() -> str:
    requested = os.getenv("AGENTHIVE_HOST", "127.0.0.1")
    allow_remote = os.getenv("AGENTHIVE_ALLOW_REMOTE_BIND", "false").lower() == "true"
    if requested in {"0.0.0.0", "::", "[::]"} and not allow_remote:
        return "127.0.0.1"
    return requested

def _find_binary(env_var: str, default_paths: list, bin_name: str) -> str:
    """Finds an executable from env var, default candidate paths, or PATH."""
    val = os.getenv(env_var)
    if val and os.path.exists(val):
        return val
    for p in default_paths:
        if os.path.exists(p):
            return p
    found = shutil.which(bin_name)
    if found:
        return found
    return default_paths[0] if default_paths else bin_name

class Settings:
    # 1. System Runtime
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    host: str = _effective_host()
    port: int = int(os.getenv("AGENTHIVE_PORT", "8000"))
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/data/agenthive.db")
    workspace_root: str = os.getenv("WORKSPACE_ROOT", str(BASE_DIR / "workspaces"))
    task_execution_enabled: bool = os.getenv("AGENTHIVE_TASK_EXECUTION_ENABLED", "false").lower() == "true"
    secure_agent_task_runner_configured: bool = os.getenv(
        "AGENTHIVE_SECURE_AGENT_TASK_RUNNER_CONFIGURED", "false"
    ).lower() == "true"
    test_runner_image: Optional[str] = os.getenv("AGENTHIVE_TEST_RUNNER_IMAGE")
    dashboard_api_token: Optional[str] = os.getenv("AGENTHIVE_DASHBOARD_API_TOKEN")
    dashboard_session_cookie_secure: bool = os.getenv(
        "AGENTHIVE_DASHBOARD_COOKIE_SECURE",
        "true" if os.getenv("ENVIRONMENT", "development").lower() == "production" else "false",
    ).lower() == "true"
    dashboard_allowed_origins: tuple = tuple(
        origin.strip()
        for origin in os.getenv(
            "AGENTHIVE_DASHBOARD_ALLOWED_ORIGINS",
            "http://127.0.0.1:8000,http://localhost:8000",
        ).split(",")
        if origin.strip() and origin.strip() != "*"
    )

    # 2. Discord Gateway
    discord_bot_token: Optional[str] = os.getenv("DISCORD_BOT_TOKEN")
    discord_application_id: Optional[str] = os.getenv("DISCORD_APPLICATION_ID")
    discord_guild_id: Optional[str] = os.getenv("DISCORD_GUILD_ID")
    discord_lounge_channel_id: Optional[str] = os.getenv("DISCORD_LOUNGE_CHANNEL_ID")
    discord_webhook_url: Optional[str] = os.getenv("DISCORD_WEBHOOK_URL")
    discord_owner_id: Optional[str] = os.getenv("DISCORD_OWNER_ID")

    # 3. Switch Collaboration Infrastructure
    # Official Switch is mandatory by default. Local transport requires an explicit
    # SWITCH_MODE=local opt-in for isolated development and tests.
    switch_mode: str = os.getenv("SWITCH_MODE", "official").lower()
    switch_core_url: str = os.getenv("SWITCH_CORE_URL", "http://127.0.0.1:8080")
    switch_ws_url: str = os.getenv("SWITCH_WS_URL", "ws://127.0.0.1:8082/events")
    switch_registration_token: Optional[str] = os.getenv("SWITCH_REGISTRATION_TOKEN")
    switch_api_key: Optional[str] = os.getenv("SWITCH_API_KEY")
    switch_console_path: str = os.getenv("SWITCH_CONSOLE_PATH", "/Applications/Switch.app")

    # 4. Agent Integrations & Binaries
    # Real Codex CLI binary (e.g. ChatGPT.app bundled codex) or direct binary
    codex_binary_path: str = _find_binary(
        "CODEX_BINARY_PATH",
        [
            "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
            "/usr/local/bin/codex",
            str(Path.home() / ".local/bin/codex")
        ],
        "codex"
    )
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_model_codex: str = os.getenv("OPENAI_MODEL_CODEX", "gpt-4o")
    codex_execution_timeout_sec: int = int(os.getenv("CODEX_EXECUTION_TIMEOUT_SEC", "120"))

    # Native AGY (Antigravity) CLI
    agy_binary_path: str = _find_binary(
        "AGY_BINARY_PATH",
        [
            str(Path.home() / ".local/bin/agy"),
            str(Path.home() / ".gemini/antigravity-cli/bin/agy"),
            "/usr/local/bin/agy"
        ],
        "agy"
    )
    agy_workspace: str = os.getenv("AGY_DEFAULT_WORKSPACE", str(BASE_DIR))

    # Google Gemini
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    gemini_model_pro: str = os.getenv("GEMINI_MODEL_PRO", "gemini-2.5-pro")
    gemini_model_flash: str = os.getenv("GEMINI_MODEL_FLASH", "gemini-3.5-flash")
    gemini_conversational_model: str = os.getenv(
        "GEMINI_CONVERSATIONAL_MODEL", os.getenv("GEMINI_MODEL_FLASH", "gemini-3.5-flash")
    )

    # GitHub Codebase Integration
    github_token: Optional[str] = os.getenv("GITHUB_TOKEN")
    github_default_repo: Optional[str] = os.getenv("GITHUB_DEFAULT_REPO")

    # Hermes Agent (Nous Research)
    hermes_daemon_url: str = os.getenv("HERMES_DAEMON_URL", "http://localhost:8686")
    hermes_daemon_token: Optional[str] = os.getenv("HERMES_DAEMON_TOKEN")
    hermes_binary_path: str = _find_binary(
        "HERMES_BINARY_PATH",
        [
            "/usr/local/bin/hermes",
            str(Path.home() / ".local/bin/hermes"),
            str(Path.home() / ".hermes/bin/hermes")
        ],
        "hermes"
    )
    hermes_memory_db: str = os.getenv("HERMES_MEMORY_DB", str(BASE_DIR / "data" / "hermes_memory.db"))

    # 5. Pony Tail Discipline
    ponytail_mode: str = os.getenv("PONYTAIL_MODE", "full")  # lite | full | ultra | off
    ponytail_enforce_stdlib: bool = os.getenv("PONYTAIL_ENFORCE_STDLIB_ONLY", "true").lower() == "true"
    ponytail_max_diff_lines: int = int(os.getenv("PONYTAIL_MAX_DIFF_LINES", "300"))

    # 6. Governance & Limits
    max_discussion_turns: int = int(os.getenv("MAX_DISCUSSION_TURNS", "6"))
    session_token_budget: int = int(os.getenv("SESSION_TOKEN_BUDGET", "100000"))

settings = Settings()

