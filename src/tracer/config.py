"""Tracer settings (pydantic-settings, env_prefix TRACER_).

One Settings class, env + .env file, an lru_cached accessor. The lock fields are read by BOTH the harness and the
server subprocess -- the harness passes them through via the subprocess env so
both duels face the identical secret.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRACER_",
        env_file=".env",
        extra="ignore",
    )

    # Capable agent (cloud Claude).
    anthropic_api_key: str = ""
    capable_model: str = "claude-sonnet-4-6"
    capable_max_tokens: int = 4096

    # Weak agent (local gemma via Ollama).
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e4b"

    # The lock.
    lock_seed: int = 42
    lock_length: int = 3
    lock_alphabet: str = "ABCDE"
    lock_max_attempts: int = 8

    # Harness guardrails.
    max_turns: int = 24
    runs_dir: str = "./runs"

    # Server-side transcript logging -- opt-in, for clients that drive the MCP
    # server directly (e.g. your own Claude via Claude Desktop / Claude Code)
    # where there's no harness Recorder. The harness leaves this off so its
    # richer Recorder (with reasoning + tokens) owns the file instead.
    server_log: bool = False
    run_label: str = "session"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
