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
```

## Configuration

All settings are read from the environment or `.env` with the `IMMEPE_` prefix.
See [.env.example](.env.example).

| Variable | Default | Description |
| --- | --- | --- |
| `IMMEPE_PROFILE_DIR` | `.whatsapp-profile` | Browser profile storing the logged-in session |
| `IMMEPE_HEADLESS` | `false` | Run Chromium without a window (only after the first login) |
| `IMMEPE_TIMEOUT_MS` | `60000` | Timeout for WhatsApp Web UI waits |
| `IMMEPE_LOG_LEVEL` | `INFO` | Logging level |

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
