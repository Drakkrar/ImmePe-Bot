from pathlib import Path

import pytest

from immepe_bot.config import Settings
from immepe_bot.whatsapp import WhatsAppClient


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run in an empty directory so a developer's local .env never leaks in."""
    monkeypatch.chdir(tmp_path)


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
