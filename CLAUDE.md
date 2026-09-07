# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CLI that automates WhatsApp Web with Playwright to send messages to your **own**
"Message yourself" chat only (reminders, logs, personal notifications). It is
deliberately not a bulk/multi-recipient tool — keep changes within that scope.

## Commands

```powershell
uv sync                             # install deps into the venv
uv run playwright install chromium  # one-time: fetch the browser Playwright drives
uv run immepe-bot <cmd>             # run the CLI (login | send | schedule | version)

# Quality gate — these four mirror CI exactly; run before considering work done:
uv run ruff check .
uv run ruff format --check .   # drop --check to auto-format
uv run mypy
uv run pytest

uv run pytest tests/test_config.py::test_settings_defaults   # single test
```

`uv run` is required for every command — the project targets Python 3.13 and there is
no activated venv assumed. mypy runs in `strict` mode and ruff enables an aggressive
lint set (`ANN`, `S`/bandit, `B`, `SIM`, `UP`, …), so annotate everything and expect
security/typing lints to gate merges.

## Architecture

Four modules in `src/immepe_bot/`, all async:

- **`cli.py`** — Typer app. Each command follows the same shape: `get_settings()` →
  `_configure_logging()` → define an inner `async def _run()` → `asyncio.run(_run())`.
  This is the only place `asyncio.run` is called.
- **`whatsapp.py`** — the core. `whatsapp_session(settings)` is an async context
  manager that launches a **persistent** Chromium context (`launch_persistent_context`
  with `user_data_dir=profile_dir`) so the logged-in session survives restarts, then
  yields a `WhatsAppClient` wrapping the Playwright `Page`. Sending is UI automation:
  locate the self-chat and message box, type the text (Shift+Enter for newlines), click
  the send button, then **block in `_wait_until_transmitted` until the message leaves the
  pending state** before returning (see gotcha below).
- **`scheduler.py`** — `run_scheduled()` opens **one** session and keeps it alive,
  driving an `AsyncIOScheduler` + `CronTrigger.from_crontab(cron)`; the job re-opens the
  self-chat and sends each fire. It blocks on `asyncio.Event().wait()` until Ctrl+C. The
  session is reused across fires rather than reconnected per job.
- **`config.py`** — `Settings` (pydantic-settings `BaseSettings`), env prefix
  `IMMEPE_`, reads `.env`. `get_settings()` is the single construction point.

### Things that will bite you

- **The selectors in `whatsapp.py` (`CHAT_LIST_SELECTOR`, `MESSAGE_BOX_SELECTOR`) are
  pinned to WhatsApp Web's live DOM.** They are the most fragile part of the codebase —
  a WhatsApp UI change breaks sending, and there is no API contract protecting them.
  When sending fails, suspect these first.
- **The self chat is matched by the user's own display name (`self_chat_title`), not by
  a "(You)" label.** That label is not present as a chat-list `title` attribute in
  current WhatsApp Web — it only appears inside the opened conversation — so it can't be
  used to locate the chat. `open_self_chat` requires `IMMEPE_SELF_CHAT_TITLE` to be set
  and raises a clear error if it is empty.
- **Do not return from `send` right after submitting — wait for delivery.** The session
  context closes the instant `send` returns; WhatsApp transmits over a WebSocket
  asynchronously, so an early return lets the browser close mid-flush and the message is
  written into the chat locally but never delivered to the phone. `_wait_until_transmitted`
  polls the just-sent message's status, keyed on the SVG `<title>` icon id
  (`wds-ic-status-pending` → a check/read icon). That id is **not** localized — the
  aria-label ("Pending"/"Read") is — so never key delivery logic on the aria text. If a
  message can't be sent it stays pending and `send` raises `PlaywrightTimeoutError` rather
  than silently succeeding.
- **First login must run with `IMMEPE_HEADLESS=false`** (a visible window is needed to
  scan the QR). Only after a session is persisted in `profile_dir` can headless be used.
- **`profile_dir` (`.whatsapp-profile`) holds live WhatsApp credentials.** It is
  gitignored; never commit it and never print its contents.

## Tests

`pytest` runs with `asyncio_mode = auto`, so `async def test_*` needs no marker. Tests
avoid launching a real browser — e.g. `test_send_rejects_empty_message` constructs a
`WhatsAppClient` with `page=None` and only exercises pure validation logic. A shared
autouse fixture `chdir`s into a tmp dir so a developer's local `.env` never leaks into
test runs. Keep new tests browser-free; assert on pure logic, not on Playwright calls.
