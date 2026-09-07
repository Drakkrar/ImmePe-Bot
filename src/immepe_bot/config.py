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
    # Locale-dependent suffix WhatsApp Web appends to your own name on the
    # "Message yourself" chat: "(You)" in English, "(Tú)" in Spanish, etc.
    # Override this to match the language of the host running the browser.
    self_chat_suffix: str = Field(default="(You)", min_length=1)


def get_settings() -> Settings:
    """Build settings from the current environment."""
    return Settings()
