# ImmePe-Bot

Automated **self**-message sender for WhatsApp. It drives your own WhatsApp Web
session with Playwright and posts notes into the "Message yourself" chat — useful
for reminders, logs and personal notifications. It does not send messages to other
people and is not a bulk/spam tool.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- A WhatsApp account you can link to WhatsApp Web

## Setup

```powershell
uv sync
uv run playwright install chromium
Copy-Item .env.example .env
uv run pre-commit install
```

## Usage

```powershell
# First run: a browser opens, scan the QR code. The session is persisted.
uv run immepe-bot login

# Send one message to yourself
uv run immepe-bot send "Remember to review the backlog"

# Send on a schedule (crontab syntax), keeps running until Ctrl+C
uv run immepe-bot schedule "Daily standup in 5 minutes" --cron "55 8 * * 1-5"

# Check the session is ready (profile exists + authenticated, not awaiting a QR scan)
uv run immepe-bot status

# Run the always-on service: a web dashboard to manage many cron jobs + the scheduler
uv run immepe-bot serve   # then open http://127.0.0.1:8000
```

## Web dashboard (`serve`)

`immepe-bot serve` runs a small local web dashboard **and** the scheduler in one
process, sharing a single WhatsApp session. Jobs are stored in a SQLite database
(`IMMEPE_DB_PATH`), so they survive restarts and can be searched quickly. From the
dashboard you can create, edit, enable/disable, search and delete jobs (each with its
own message and crontab), and hit **Send now** to test one immediately. Changes take
effect live — no restart needed.

Before serving, run `immepe-bot login` once (visible window) to persist the session.
`serve` refuses to start and tells you to log in if the profile is missing or the
session needs a fresh QR scan.

## Docker

The service can run in a container. **Log in on the host first** so the session profile
exists, then start the container, which reuses it headlessly:

```powershell
uv run immepe-bot login          # host, visible window — scan the QR once
docker compose up --build        # dashboard on http://localhost:8000
```

`docker-compose.yml` mounts `./.whatsapp-profile` (the session) and `./data` (the jobs
database) as volumes and exposes port 8000. Do not run the host `login`/`status` while
the container is running — both would fight over the Chromium profile lock.

## Configuration

All settings are read from the environment or `.env` with the `IMMEPE_` prefix.
See [.env.example](.env.example).

| Variable | Default | Description |
| --- | --- | --- |
| `IMMEPE_PROFILE_DIR` | `.whatsapp-profile` | Browser profile storing the logged-in session |
| `IMMEPE_HEADLESS` | `false` | Run Chromium without a window (only after the first login) |
| `IMMEPE_TIMEOUT_MS` | `60000` | Timeout for WhatsApp Web UI waits |
| `IMMEPE_LOG_LEVEL` | `INFO` | Logging level |
| `IMMEPE_SELF_CHAT_TITLE` | _(required for send/schedule)_ | Exact label on your "Message yourself" chat, i.e. your own WhatsApp display name |
| `IMMEPE_DB_PATH` | `jobs.db` | SQLite file storing the dashboard's scheduled jobs |
| `IMMEPE_WEB_HOST` | `127.0.0.1` | Address the `serve` dashboard binds to (`0.0.0.0` in Docker) |
| `IMMEPE_WEB_PORT` | `8000` | Port the `serve` dashboard listens on |
| `IMMEPE_PROBE_TIMEOUT_MS` | `15000` | Timeout for the authenticated-vs-QR session probe |
| `IMMEPE_MISFIRE_GRACE_S` | `300` | Grace period for a scheduled fire missed while busy/down |

The profile directory contains credentials for your WhatsApp session. Keep it out
of version control and off shared machines.

## Development

```powershell
uv run ruff check .
uv run ruff format .
uv run mypy
uv run pytest
```

## Disclaimer

Automating WhatsApp Web is not officially supported by WhatsApp. Use this on your
own account, at your own risk, and only for messages to yourself.

## License

MIT
