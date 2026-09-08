"""The long-running bot service: one WhatsApp session driven by a persisted schedule.

`BotService` owns the single shared `WhatsAppClient`, the `AsyncIOScheduler`, and the
`JobRepository`. Every send — whether a scheduled fire or a UI "send now" — funnels
through `send_message`, serialized by one `asyncio.Lock`, because the Playwright `Page`
is a single shared resource that must not be driven concurrently.

The `jobs` table is the source of truth: `sync_from_db` rebuilds the in-memory scheduler
from it on startup, and the web layer calls `apply_job`/`unschedule_job` after every
CRUD op so changes take effect live without a restart.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from immepe_bot.config import Settings
from immepe_bot.models import Job, JobStatus
from immepe_bot.store import JobRepository
from immepe_bot.whatsapp import WhatsAppClient

logger = logging.getLogger(__name__)


@dataclass
class BotService:
    """Coordinates the scheduler, the job store and the shared WhatsApp session."""

    settings: Settings
    repo: JobRepository
    scheduler: AsyncIOScheduler
    client: WhatsAppClient
    _send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send_message(self, message: str) -> None:
        """Open the self chat and send `message`, serialized on the shared Page."""
        async with self._send_lock:
            await self.client.open_self_chat()
            await self.client.send(message)

    async def run_job(self, job_id: str) -> None:
        """APScheduler callback: send the job's message and record the outcome."""
        job = self.repo.get(job_id)
        if job is None or not job.enabled:
            return
        ran_at = datetime.now(tz=UTC)
        try:
            await self.send_message(job.message)
        except Exception as exc:  # a single failure must not kill the scheduler
            self.repo.record_run(
                job_id, status=JobStatus.ERROR, error=str(exc), ran_at=ran_at
            )
            logger.exception("Scheduled send failed for job %s", job_id)
        else:
            self.repo.record_run(
                job_id, status=JobStatus.SUCCESS, error=None, ran_at=ran_at
            )
        finally:
            self._refresh_next_run(job_id)

    def schedule_job(self, job: Job) -> None:
        """Add or replace the APScheduler entry for an enabled job."""
        self.scheduler.add_job(
            self.run_job,
            CronTrigger.from_crontab(job.cron),
            id=job.id,
            args=[job.id],
            replace_existing=True,
            misfire_grace_time=self.settings.misfire_grace_s,
            coalesce=True,
        )
        self._refresh_next_run(job.id)

    def unschedule_job(self, job_id: str) -> None:
        """Remove the APScheduler entry if present and clear the cached next run."""
        if self.scheduler.get_job(job_id) is not None:
            self.scheduler.remove_job(job_id)
        self.repo.set_next_run(job_id, None)

    def apply_job(self, job: Job) -> None:
        """Schedule the job when enabled, otherwise ensure it is unscheduled."""
        if job.enabled:
            self.schedule_job(job)
        else:
            self.unschedule_job(job.id)

    def sync_from_db(self) -> None:
        """Rebuild the scheduler from every enabled job in the store."""
        for job in self.repo.list(enabled_only=True):
            self.schedule_job(job)

    def _refresh_next_run(self, job_id: str) -> None:
        scheduled = self.scheduler.get_job(job_id)
        # `next_run_time` is unset (raises) for a job still pending on a not-yet-started
        # scheduler, so read it defensively and cache None until it is computed.
        next_run: datetime | None = (
            getattr(scheduled, "next_run_time", None) if scheduled is not None else None
        )
        self.repo.set_next_run(job_id, next_run)
