"""Pre-authentication checks shared by the CLI, the `status` command and `serve`.

Two independent checks answer "can we actually send right now?":

1. `check_profile_dir` — a cheap, offline heuristic: does `IMMEPE_PROFILE_DIR` hold a
   persisted browser session at all? It keys on Chromium/WhatsApp profile artifacts, not
   the top-level directory, because `whatsapp_session` unconditionally `mkdir`s the dir.
2. `check_session_status` — the authoritative test: launch the persistent context and
   probe whether WhatsApp Web is authenticated or is showing a QR (without blocking on a
   human scan).

`guard_message` is a pure decision function (no browser) so every branch is testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from immepe_bot.config import Settings
from immepe_bot.whatsapp import SessionStatus, whatsapp_session

# The WhatsApp login is persisted in this IndexedDB store inside the Chromium profile.
# Its presence is the strongest offline signal that a session was ever established.
_SESSION_ARTIFACT = (
    Path("Default") / "IndexedDB" / "https_web.whatsapp.com_0.indexeddb.leveldb"
)


class PreflightError(RuntimeError):
    """Raised when the profile/session is not ready to send messages."""


@dataclass(frozen=True, slots=True)
class ProfileCheck:
    """Outcome of the offline profile-directory inspection."""

    profile_dir: Path
    exists: bool
    has_session: bool


def _dir_has_entries(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def check_profile_dir(settings: Settings) -> ProfileCheck:
    """Inspect `IMMEPE_PROFILE_DIR` for a persisted session — no browser launched."""
    profile_dir = settings.profile_dir
    exists = profile_dir.is_dir()
    # Primary signal: the WhatsApp IndexedDB store. Fallback: any populated Default/
    # profile (a freshly mkdir'd, never-launched dir has neither).
    has_session = _dir_has_entries(profile_dir / _SESSION_ARTIFACT) or _dir_has_entries(
        profile_dir / "Default"
    )
    return ProfileCheck(profile_dir=profile_dir, exists=exists, has_session=has_session)


async def check_session_status(settings: Settings) -> SessionStatus:
    """Launch the persistent context and probe authenticated-vs-QR (non-blocking)."""
    async with whatsapp_session(settings, wait_ready=False) as client:
        return await client.probe_status(settings.probe_timeout_ms)


def guard_message(check: ProfileCheck, status: SessionStatus | None) -> str | None:
    """Return an actionable error string, or None when ready to send.

    `status` may be None when the offline check already failed (so no probe was run).
    """
    if not check.has_session:
        return (
            f"No persisted WhatsApp session found in {check.profile_dir}. "
            "Run `immepe-bot login` (with a visible window) and scan the QR code first."
        )
    if status is SessionStatus.NEEDS_QR:
        return (
            "WhatsApp session is not linked or has expired. "
            "Run `immepe-bot login` and scan the QR code to re-link the device."
        )
    if status is SessionStatus.UNKNOWN:
        return (
            "Could not determine the WhatsApp session status (timed out or the page "
            "changed). Check your connectivity, then run `immepe-bot login` if needed."
        )
    return None


async def ensure_ready(settings: Settings) -> None:
    """Raise `PreflightError` unless both checks pass. Guard for send/schedule/serve."""
    check = check_profile_dir(settings)
    status = await check_session_status(settings) if check.has_session else None
    message = guard_message(check, status)
    if message is not None:
        raise PreflightError(message)
