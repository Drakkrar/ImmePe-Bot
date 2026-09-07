"""Cron-based scheduling of self-messages."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from immepe_bot.config import Settings
from immepe_bot.whatsapp import whatsapp_session

logger = logging.getLogger(__name__)


async def run_scheduled(settings: Settings, message: str, cron: str) -> None:
    """Keep one WhatsApp session open and send `message` on the `cron` schedule."""
    trigger = CronTrigger.from_crontab(cron)

    async with whatsapp_session(settings) as client:
        scheduler = AsyncIOScheduler()

        async def job() -> None:
            try:
                await client.open_self_chat()
                await client.send(message)
            except Exception:
                logger.exception("Scheduled send failed")

        scheduler.add_job(job, trigger=trigger, id="self-message")
        scheduler.start()
        logger.info("Scheduler started with cron %r; press Ctrl+C to stop", cron)

        try:
            await asyncio.Event().wait()
        finally:
            scheduler.shutdown(wait=False)
