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
    host: str = os.getenv("AGENTHIVE_HOST", "0.0.0.0")
    port: int = int(os.getenv("AGENTHIVE_PORT", "8000"))
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/data/agenthive.db")
    workspace_root: str = os.getenv("WORKSPACE_ROOT", str(BASE_DIR / "workspaces"))

    # 2. Discord Gateway
    discord_bot_token: Optional[str] = os.getenv("DISCORD_BOT_TOKEN")
    discord_application_id: Optional[str] = os.getenv("DISCORD_APPLICATION_ID")
    discord_guild_id: Optional[str] = os.getenv("DISCORD_GUILD_ID")
    discord_lounge_channel_id: Optional[str] = os.getenv("DISCORD_LOUNGE_CHANNEL_ID")
    discord_webhook_url: Optional[str] = os.getenv("DISCORD_WEBHOOK_URL")

    # 3. Switch Collaboration Infrastructure
    # switch_mode: "auto" | "official" | "local"
    switch_mode: str = os.getenv("SWITCH_MODE", "auto")
    switch_core_url: str = os.getenv("SWITCH_CORE_URL", "http://localhost:8000")
    switch_ws_url: str = os.getenv("SWITCH_WS_URL", "ws://localhost:8000/switch/ws")
    switch_api_key: str = os.getenv("SWITCH_API_KEY", "agenthive-switch-secret-key")
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
    gemini_model_flash: str = os.getenv("GEMINI_MODEL_FLASH", "gemini-2.5-flash")

    # Hermes Agent (Nous Research)
    hermes_daemon_url: str = os.getenv("HERMES_DAEMON_URL", "http://localhost:8686")
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

