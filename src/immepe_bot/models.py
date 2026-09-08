"""Domain models for scheduled self-message jobs.

`Job` is the persisted row (source of truth in SQLite); `JobCreate`/`JobUpdate` are the
validated inputs used by both the CLI and the web dashboard. Cron and message validation
live here so a bad value is rejected identically no matter which layer submits it,
mirroring the "clear ValueError" style of `WhatsAppClient.open_self_chat`/`send`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, ConfigDict, field_validator


class JobStatus(StrEnum):
    """Outcome of the most recent run of a job."""

    SUCCESS = "success"
    ERROR = "error"


def _validate_cron(value: str) -> str:
    """Return `value` if it is a valid 5-field crontab expression, else raise.

    Reuses APScheduler's own parser (`CronTrigger.from_crontab`) — the same call the
    scheduler makes — so what validates here is exactly what will schedule later.
    """
    expression = value.strip()
    if not expression:
        raise ValueError("Cron expression must not be empty")
    try:
        CronTrigger.from_crontab(expression)
    except ValueError as exc:
        raise ValueError(f"Invalid cron expression {value!r}: {exc}") from exc
    return expression


def _validate_message(value: str) -> str:
    """Reject whitespace-only messages, matching `WhatsAppClient.send`."""
    if not value.strip():
        raise ValueError("Message must not be empty")
    return value


class Job(BaseModel):
    """A persisted scheduled job. Immutable snapshot of a `jobs` table row."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    message: str
    cron: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    last_status: JobStatus | None = None
    last_error: str | None = None
    next_run_at: datetime | None = None


class JobCreate(BaseModel):
    """Validated input for creating a job."""

    name: str
    message: str
    cron: str
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be empty")
        return value

    @field_validator("message")
    @classmethod
    def _message_not_empty(cls, value: str) -> str:
        return _validate_message(value)

    @field_validator("cron")
    @classmethod
    def _cron_valid(cls, value: str) -> str:
        return _validate_cron(value)


class JobUpdate(BaseModel):
    """Validated input for a partial update; every field is optional."""

    name: str | None = None
    message: str | None = None
    cron: str | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Name must not be empty")
        return value

    @field_validator("message")
    @classmethod
    def _message_not_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_message(value)

    @field_validator("cron")
    @classmethod
    def _cron_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_cron(value)
