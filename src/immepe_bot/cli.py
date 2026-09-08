"""Command line interface."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

import typer

from immepe_bot import __version__
from immepe_bot.config import Settings, get_settings
from immepe_bot.preflight import (
    check_profile_dir,
    check_session_status,
    guard_message,
)
from immepe_bot.scheduler import run_scheduled
from immepe_bot.whatsapp import whatsapp_session

app = typer.Typer(
    name="immepe-bot",
    help="Send scheduled notes to your own WhatsApp chat via WhatsApp Web.",
    no_args_is_help=True,
)


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


def _require_profile_session(settings: Settings) -> None:
    """Exit early (offline) when no persisted session exists, before launching."""
    check = check_profile_dir(settings)
    if not check.has_session:
        typer.echo(guard_message(check, None))
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command()
def login() -> None:
    """Open WhatsApp Web so you can scan the QR code and persist the session."""
    settings = get_settings()
    _configure_logging(settings)

    async def _run() -> None:
        async with whatsapp_session(settings):
            typer.echo("Session stored in " + str(settings.profile_dir.resolve()))

    asyncio.run(_run())


@app.command()
def send(
    message: Annotated[str, typer.Argument(help="Text to send to yourself.")],
) -> None:
    """Send a single message to your own WhatsApp chat."""
    settings = get_settings()
    _configure_logging(settings)
    _require_profile_session(settings)

    async def _run() -> None:
        async with whatsapp_session(settings) as client:
            await client.open_self_chat()
            await client.send(message)

    asyncio.run(_run())


@app.command()
def schedule(
    message: Annotated[str, typer.Argument(help="Text to send to yourself.")],
    cron: Annotated[
        str, typer.Option("--cron", help="Crontab expression, e.g. '0 9 * * *'.")
    ],
) -> None:
    """Send a message to yourself repeatedly on a cron schedule."""
    settings = get_settings()
    _configure_logging(settings)
    _require_profile_session(settings)
    asyncio.run(run_scheduled(settings, message, cron))


@app.command()
def status() -> None:
    """Check whether the WhatsApp session is ready (profile + authentication)."""
    settings = get_settings()
    _configure_logging(settings)

    async def _run() -> None:
        check = check_profile_dir(settings)
        session_status = (
            await check_session_status(settings) if check.has_session else None
        )
        message = guard_message(check, session_status)
        if message is None:
            typer.echo("OK: WhatsApp session is authenticated and ready.")
            return
        typer.echo(message)
        raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command()
def serve() -> None:
    """Run the web dashboard + scheduler daemon (one shared WhatsApp session)."""
    settings = get_settings()
    _configure_logging(settings)

    import uvicorn

    from immepe_bot.web.app import build_app

    application = build_app(settings)
    config = uvicorn.Config(
        application,
        host=settings.web_host,
        port=settings.web_port,
        log_level=settings.log_level.lower(),
    )
    asyncio.run(uvicorn.Server(config).serve())


def main() -> None:
    """Console-script entry point."""
    app()
