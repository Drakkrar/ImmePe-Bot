"""SQLite-backed repository of scheduled jobs.

Uses the stdlib `sqlite3` driver (no extra dependency) with a thin, fully typed
repository. Every statement is qmark-parameterized — never string-built SQL — so it
stays clean under ruff's bandit (`S608`) checks. The `jobs` table is the single source
of truth; APScheduler is rebuilt from it on startup.
"""

from __future__ import annotations

import builtins
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from immepe_bot.models import Job, JobCreate, JobStatus, JobUpdate

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT    PRIMARY KEY,
    name         TEXT    NOT NULL,
    message      TEXT    NOT NULL,
    cron         TEXT    NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    last_run_at  TEXT,
    last_status  TEXT,
    last_error   TEXT,
    next_run_at  TEXT
)
"""
_CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_jobs_enabled ON jobs(enabled)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_name ON jobs(name)",
)

# Columns a partial update may touch, keyed by the model field name. The values are
# fixed SQL identifiers (not user input), so building the SET clause from them is safe.
_UPDATABLE_COLUMNS = ("name", "message", "cron", "enabled")


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class JobRepository:
    """Typed CRUD + search over the `jobs` table."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        # A single shared connection guarded by a lock: `check_same_thread=False` lets
        # APScheduler's worker threads and the web handlers use it; the lock serializes
        # access so concurrent writes cannot interleave.
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    @property
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("JobRepository is not initialized; call initialize()")
        return self._conn

    def initialize(self) -> None:
        """Open the connection and create the schema if needed (idempotent)."""
        if self._conn is not None:
            return
        if self._db_path.parent != Path():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_CREATE_TABLE)
        for statement in _CREATE_INDEXES:
            conn.execute(statement)
        conn.commit()
        self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def create(self, data: JobCreate) -> Job:
        now = _utcnow()
        job = Job(
            id=uuid.uuid4().hex,
            name=data.name,
            message=data.message,
            cron=data.cron,
            enabled=data.enabled,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._connection.execute(
                "INSERT INTO jobs (id, name, message, cron, enabled, created_at, "
                "updated_at, last_run_at, last_status, last_error, next_run_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)",
                (
                    job.id,
                    job.name,
                    job.message,
                    job.cron,
                    int(job.enabled),
                    _iso(job.created_at),
                    _iso(job.updated_at),
                ),
            )
            self._connection.commit()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return _row_to_job(row) if row is not None else None

    def list(self, *, enabled_only: bool = False) -> builtins.list[Job]:
        # `builtins.list[...]` because the method name `list` shadows the builtin inside
        # this class's annotation scope.
        query = "SELECT * FROM jobs"
        params: tuple[object, ...] = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at ASC"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [_row_to_job(row) for row in rows]

    def search(self, query: str) -> builtins.list[Job]:
        pattern = f"%{query}%"
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM jobs WHERE name LIKE ? OR message LIKE ? "
                "ORDER BY created_at ASC",
                (pattern, pattern),
            ).fetchall()
        return [_row_to_job(row) for row in rows]

    def update(self, job_id: str, data: JobUpdate) -> Job | None:
        changes = data.model_dump(exclude_unset=True)
        columns = [col for col in _UPDATABLE_COLUMNS if col in changes]
        if not columns:
            return self.get(job_id)
        assignments = ", ".join(f"{col} = ?" for col in columns)
        values: list[object] = [
            int(changes[col]) if col == "enabled" else changes[col] for col in columns
        ]
        values.append(_iso(_utcnow()))
        values.append(job_id)
        with self._lock:
            cursor = self._connection.execute(
                f"UPDATE jobs SET {assignments}, updated_at = ? WHERE id = ?",  # noqa: S608
                values,
            )
            self._connection.commit()
            changed = cursor.rowcount
        if not changed:
            return None
        return self.get(job_id)

    def set_enabled(self, job_id: str, enabled: bool) -> Job | None:
        return self.update(job_id, JobUpdate(enabled=enabled))

    def delete(self, job_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM jobs WHERE id = ?", (job_id,)
            )
            self._connection.commit()
            return cursor.rowcount > 0

    def record_run(
        self,
        job_id: str,
        *,
        status: JobStatus,
        error: str | None,
        ran_at: datetime,
    ) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE jobs SET last_run_at = ?, last_status = ?, last_error = ? "
                "WHERE id = ?",
                (_iso(ran_at), status.value, error, job_id),
            )
            self._connection.commit()

    def set_next_run(self, job_id: str, next_run_at: datetime | None) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE jobs SET next_run_at = ? WHERE id = ?",
                (_iso(next_run_at), job_id),
            )
            self._connection.commit()


def _row_to_job(row: sqlite3.Row) -> Job:
    """Convert a raw DB row into a validated `Job` (int→bool, ISO strings→datetime)."""
    data: dict[str, object] = dict(row)
    data["enabled"] = bool(row["enabled"])
    return Job.model_validate(data)
