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
uv run immepe-bot <cmd>             # login | send | schedule | status | serve | version

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

Modules in `src/immepe_bot/`, all async:

- **`cli.py`** — Typer app. Each command follows the same shape: `get_settings()` →
  `_configure_logging()` → define an inner `async def _run()` → `asyncio.run(_run())`.
  This is the only place `asyncio.run` is called (`serve` runs it via uvicorn's server).
- **`whatsapp.py`** — the core. `whatsapp_session(settings, *, wait_ready=True)` is an
  async context manager that launches a **persistent** Chromium context
  (`launch_persistent_context` with `user_data_dir=profile_dir`) so the logged-in session
  survives restarts, then yields a `WhatsAppClient` wrapping the Playwright `Page`.
  `wait_ready=False` skips the blocking chat-list wait (used by the status probe and
  `serve`). Sending is UI automation: locate the self-chat and message box, type the text
  (Shift+Enter for newlines), click the send button, then **block in
  `_wait_until_transmitted` until the message leaves the pending state** before returning
  (see gotcha below). `WhatsAppClient.probe_status()` races the chat-list selector against
  `QR_CODE_SELECTOR` to return `SessionStatus` (AUTHENTICATED/NEEDS_QR/UNKNOWN) without
  ever blocking on a human QR scan.
- **`scheduler.py`** — `run_scheduled()` is the legacy single-message foreground mode
  behind the `schedule` command. Superseded by `serve` for persistent, multi-job,
  UI-managed use; kept for quick one-off cron sends without the DB/web stack.
- **`config.py`** — `Settings` (pydantic-settings `BaseSettings`), env prefix
  `IMMEPE_`, reads `.env`. `get_settings()` is the single construction point.
- **`models.py`** — pydantic `Job`/`JobCreate`/`JobUpdate` + `JobStatus`. Cron and empty-
  message validation live here (via `CronTrigger.from_crontab`), so bad input is rejected
  identically from the CLI and the web layer.
- **`store.py`** — `JobRepository`, a thin typed wrapper over stdlib `sqlite3` (no ORM).
  The `jobs` table is the **single source of truth**; all SQL is qmark-parameterized. Note
  the method is named `list`, which shadows the builtin inside the class, so its return
  annotation uses `builtins.list[Job]`.
- **`preflight.py`** — the two pre-auth checks: `check_profile_dir` (offline; keys on
  Chromium/WhatsApp profile artifacts, not the top-level dir, since `whatsapp_session`
  always `mkdir`s it) and `check_session_status` (launches a probe context). `guard_message`
  is a **pure** decision function (unit-tested); `ensure_ready` composes both and raises
  `PreflightError`. Surfaced as `immepe-bot status` and enforced at `serve` startup.
- **`service.py`** — `BotService` owns the single shared `WhatsAppClient`, the
  `AsyncIOScheduler`, and the `JobRepository`. `sync_from_db` rebuilds the scheduler from
  the table on startup; the web layer calls `apply_job`/`unschedule_job` after every CRUD
  op so edits take effect live.
- **`web/`** — FastAPI dashboard. `app.py::build_app(settings, *, service=None)` wires the
  routes + Jinja2 templates + static files; its `lifespan` opens the one session, runs both
  pre-auth checks, starts the scheduler, and tears down on shutdown. `routes.py` is the job
  CRUD + `send-now` + `/healthz`. Passing `service=` injects a ready `BotService` and skips
  the browser — the seam the web tests use.

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
- **Headless needs user-agent masking.** WhatsApp Web serves an "unsupported browser"
  page to a `HeadlessChrome` user agent, so the chat list never loads and
  `wait_until_ready` times out. `whatsapp_session` therefore only in headless mode
  launches with `user_agent` = this Chromium's UA with `HeadlessChrome`→`Chrome`
  (via `_headless_user_agent`, a throwaway launch so the version isn't hard-coded) plus
  `--disable-blink-features=AutomationControlled`. Don't hard-code a UA — WhatsApp gates
  on the Chrome version, so it must track the installed Chromium.
- **`profile_dir` (`.whatsapp-profile`) holds live WhatsApp credentials.** It is
  gitignored; never commit it and never print its contents.
- **`QR_CODE_SELECTOR` is the newest fragile selector** (joins `CHAT_LIST_SELECTOR`/
  `MESSAGE_BOX_SELECTOR`). It is best-effort only: a wrong guess just degrades the
  `probe_status` result to `UNKNOWN`; it never affects sending.
- **`serve` is one process, one event loop, one WhatsApp session.** The Playwright `Page`
  is a single shared resource, so **every** send — scheduled fire *and* the UI "send now"
  — must go through `BotService.send_message`, which serializes them on one `asyncio.Lock`.
  A send that stays pending holds that lock until `_wait_until_transmitted` times out.
- **The `jobs` SQLite table is the source of truth; APScheduler is in-memory.** It is
  rebuilt from the table on startup and mutated live on every web CRUD op — never persist
  schedule state only in APScheduler.
- **Docker reuses a host login.** Run `immepe-bot login` on the host to populate
  `.whatsapp-profile`, then the container runs headless against the mounted profile. Never
  run the host `login`/`status` and the container at once — they collide on the profile
  `LOCK`. The compose healthcheck hits `/healthz` over HTTP, not `status`, for the same
  reason.

## Tests

`pytest` runs with `asyncio_mode = auto`, so `async def test_*` needs no marker. Tests
avoid launching a real browser — e.g. `test_send_rejects_empty_message` constructs a
`WhatsAppClient` with `page=None` and only exercises pure validation logic; the web tests
build the app with an injected `BotService` (a real repo + an `AsyncMock` WhatsApp client)
so no browser starts. Shared fixtures live in `tests/conftest.py`: the autouse
`isolated_cwd` `chdir`s into a tmp dir so a developer's local `.env` never leaks, and
`repo` yields an initialized `JobRepository` on a throwaway sqlite file. Keep new tests
browser-free; assert on pure logic, not on Playwright calls.
