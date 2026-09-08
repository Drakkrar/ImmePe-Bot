from pathlib import Path

import pytest

from immepe_bot.config import Settings
from immepe_bot.whatsapp import WhatsAppClient


def test_settings_read_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMEPE_HEADLESS", "true")
    monkeypatch.setenv("IMMEPE_PROFILE_DIR", "custom-profile")

    settings = Settings()

    assert settings.headless is True
    assert settings.profile_dir == Path("custom-profile")


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.headless is False
    assert settings.timeout_ms == 60_000
    assert settings.log_level == "INFO"
    assert settings.self_chat_title == ""
    assert settings.db_path == Path("jobs.db")
    assert settings.web_host == "127.0.0.1"
    assert settings.web_port == 8000
    assert settings.probe_timeout_ms == 15_000
    assert settings.misfire_grace_s == 300


def test_service_settings_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMEPE_DB_PATH", "custom/jobs.sqlite")
    monkeypatch.setenv("IMMEPE_WEB_HOST", "192.168.0.5")
    monkeypatch.setenv("IMMEPE_WEB_PORT", "9001")
    monkeypatch.setenv("IMMEPE_PROBE_TIMEOUT_MS", "2500")
    monkeypatch.setenv("IMMEPE_MISFIRE_GRACE_S", "42")

    settings = Settings()

    assert settings.db_path == Path("custom/jobs.sqlite")
    assert settings.web_host == "192.168.0.5"
    assert settings.web_port == 9001
    assert settings.probe_timeout_ms == 2500
    assert settings.misfire_grace_s == 42


def test_self_chat_title_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMMEPE_SELF_CHAT_TITLE", "Pancho Pistolas")

    assert Settings().self_chat_title == "Pancho Pistolas"


async def test_send_rejects_empty_message() -> None:
    client = WhatsAppClient(page=None, settings=Settings())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="must not be empty"):
        await client.send("   ")


async def test_open_self_chat_requires_title() -> None:
    client = WhatsAppClient(page=None, settings=Settings())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="self_chat_title"):
        await client.open_self_chat()
