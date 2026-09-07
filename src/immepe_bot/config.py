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


def get_settings() -> Settings:
    """Build settings from the current environment."""
    return Settings()
