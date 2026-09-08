from pathlib import Path

import pytest

from immepe_bot import preflight
from immepe_bot.config import Settings
from immepe_bot.preflight import (
    PreflightError,
    ProfileCheck,
    ensure_ready,
    guard_message,
)
from immepe_bot.whatsapp import SessionStatus


def _check(*, has_session: bool) -> ProfileCheck:
    return ProfileCheck(
        profile_dir=Path("profile"), exists=True, has_session=has_session
    )


def test_guard_message_no_session_mentions_login() -> None:
    message = guard_message(_check(has_session=False), None)

    assert message is not None
    assert "login" in message


def test_guard_message_needs_qr_mentions_login() -> None:
    message = guard_message(_check(has_session=True), SessionStatus.NEEDS_QR)

    assert message is not None
    assert "login" in message


def test_guard_message_unknown_is_reported() -> None:
    message = guard_message(_check(has_session=True), SessionStatus.UNKNOWN)

    assert message is not None


def test_guard_message_authenticated_is_none() -> None:
    assert guard_message(_check(has_session=True), SessionStatus.AUTHENTICATED) is None


async def test_ensure_ready_passes_when_authenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_profile(_: Settings) -> ProfileCheck:
        return _check(has_session=True)

    async def fake_status(_: Settings) -> SessionStatus:
        return SessionStatus.AUTHENTICATED

    monkeypatch.setattr(preflight, "check_profile_dir", fake_profile)
    monkeypatch.setattr(preflight, "check_session_status", fake_status)

    await ensure_ready(Settings())  # must not raise


async def test_ensure_ready_raises_when_needs_qr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_profile(_: Settings) -> ProfileCheck:
        return _check(has_session=True)

    async def fake_status(_: Settings) -> SessionStatus:
        return SessionStatus.NEEDS_QR

    monkeypatch.setattr(preflight, "check_profile_dir", fake_profile)
    monkeypatch.setattr(preflight, "check_session_status", fake_status)

    with pytest.raises(PreflightError):
        await ensure_ready(Settings())


async def test_ensure_ready_skips_probe_without_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probed = False

    def fake_profile(_: Settings) -> ProfileCheck:
        return _check(has_session=False)

    async def fake_status(_: Settings) -> SessionStatus:
        nonlocal probed
        probed = True
        return SessionStatus.AUTHENTICATED

    monkeypatch.setattr(preflight, "check_profile_dir", fake_profile)
    monkeypatch.setattr(preflight, "check_session_status", fake_status)

    with pytest.raises(PreflightError):
        await ensure_ready(Settings())
    assert probed is False
