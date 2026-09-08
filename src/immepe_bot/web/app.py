"""FastAPI application factory and lifespan for the `serve` daemon.

`build_app` wires the routes, templates and static files. Its lifespan opens the single
long-lived WhatsApp session, runs the two pre-auth checks against it, starts the
scheduler, and tears everything down on shutdown — all on one asyncio event loop.

Passing `service=` injects a ready-made `BotService` and skips the browser entirely;
this is the seam the web tests use to stay browser-free.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from immepe_bot.config import Settings
from immepe_bot.preflight import PreflightError, check_profile_dir, guard_message
from immepe_bot.service import BotService
from immepe_bot.store import JobRepository
from immepe_bot.web.routes import router
from immepe_bot.whatsapp import whatsapp_session

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"


def build_app(settings: Settings, *, service: BotService | None = None) -> FastAPI:
    """Construct the dashboard app. With `service` set, no browser is launched."""
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.templates = templates

        if service is not None:
            app.state.service = service
            yield
            return

        repo = JobRepository(settings.db_path)
        repo.initialize()

        # Check 1 (offline): a persisted session must exist before we launch anything.
        profile = check_profile_dir(settings)
        if not profile.has_session:
            raise PreflightError(
                guard_message(profile, None) or "WhatsApp session not ready"
            )

        # One session for the whole daemon lifetime.
        async with whatsapp_session(settings, wait_ready=False) as client:
            # Check 2 (authoritative) on the SAME client — launching a second context
            # would collide on the profile LOCK.
            status = await client.probe_status(settings.probe_timeout_ms)
            guard = guard_message(profile, status)
            if guard is not None:
                raise PreflightError(guard)
            await client.wait_until_ready()

            scheduler = AsyncIOScheduler()
            scheduler.start()
            bot = BotService(
                settings=settings, repo=repo, scheduler=scheduler, client=client
            )
            bot.sync_from_db()
            app.state.service = bot
            try:
                yield
            finally:
                scheduler.shutdown(wait=False)
        repo.close()

    app = FastAPI(title="ImmePe-Bot", lifespan=lifespan)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    return app
