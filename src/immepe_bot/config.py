"""Application settings loaded from environment variables / `.env`."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the WhatsApp Web automation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="IMMEPE_",
        extra="ignore",
    )

    # Browser profile directory holding the authenticated WhatsApp Web session.
    profile_dir: Path = Field(default=Path(".whatsapp-profile"))
    headless: bool = Field(default=False)
    # Milliseconds to wait for WhatsApp Web UI elements.
    timeout_ms: int = Field(default=60_000, gt=0)
    log_level: str = Field(default="INFO")
    # Exact label on your "Message yourself" chat in the chat list — i.e. your own
    # WhatsApp display name (e.g. "Pancho Pistolas"). This is locale-independent: it
    # is your name, not translated UI chrome, so it works on any host language.
    # Required for `send`/`schedule`; find it at the top of your WhatsApp chat list.
    self_chat_title: str = Field(default="")

    # SQLite file that stores the scheduled jobs managed by the `serve` dashboard.
    db_path: Path = Field(default=Path("jobs.db"))
    # Address the `serve` web dashboard binds to. Default to localhost; the Docker
    # image sets IMMEPE_WEB_HOST=0.0.0.0 via env so no bind-all literal lives in code.
    web_host: str = Field(default="127.0.0.1")
    web_port: int = Field(default=8000, gt=0, le=65535)
    # Short, non-blocking timeout for the session status probe (authenticated vs. QR).
    # Deliberately distinct from `timeout_ms`, which governs the long UI waits.
    probe_timeout_ms: int = Field(default=15_000, gt=0)
    # Grace period (seconds) for a scheduled fire that the service missed while busy or
    # briefly down, passed to APScheduler as `misfire_grace_time`.
    misfire_grace_s: int = Field(default=300, gt=0)


def get_settings() -> Settings:
    """Build settings from the current environment."""
    return Settings()
