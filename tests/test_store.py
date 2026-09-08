from datetime import UTC, datetime

import pytest

from immepe_bot.models import JobCreate, JobStatus, JobUpdate
from immepe_bot.store import JobRepository


def test_create_and_get_roundtrip(repo: JobRepository) -> None:
    job = repo.create(
        JobCreate(name="Timesheet", message="Fill the timesheet", cron="0 9 * * 1-5")
    )

    fetched = repo.get(job.id)

    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.name == "Timesheet"
    assert fetched.message == "Fill the timesheet"
    assert fetched.cron == "0 9 * * 1-5"
    assert fetched.enabled is True
    assert fetched.last_status is None


def test_get_unknown_returns_none(repo: JobRepository) -> None:
    assert repo.get("does-not-exist") is None


def test_list_orders_by_creation(repo: JobRepository) -> None:
    first = repo.create(JobCreate(name="A", message="a", cron="* * * * *"))
    second = repo.create(JobCreate(name="B", message="b", cron="* * * * *"))

    ids = [job.id for job in repo.list()]

    assert ids == [first.id, second.id]


def test_list_enabled_only(repo: JobRepository) -> None:
    enabled = repo.create(JobCreate(name="on", message="x", cron="* * * * *"))
    repo.create(JobCreate(name="off", message="y", cron="* * * * *", enabled=False))

    result = repo.list(enabled_only=True)

    assert [job.id for job in result] == [enabled.id]


def test_search_matches_name_and_message(repo: JobRepository) -> None:
    by_name = repo.create(JobCreate(name="Standup", message="hello", cron="* * * * *"))
    by_msg = repo.create(
        JobCreate(name="Other", message="join the standup call", cron="* * * * *")
    )
    repo.create(JobCreate(name="Unrelated", message="nothing", cron="* * * * *"))

    found = {job.id for job in repo.search("standup")}

    assert found == {by_name.id, by_msg.id}


def test_search_is_parameterized_against_injection(repo: JobRepository) -> None:
    quoted = repo.create(
        JobCreate(name="O'Brien's job", message="msg", cron="* * * * *")
    )

    # A value with a quote must be treated as data, not SQL.
    found = repo.search("O'Brien")

    assert [job.id for job in found] == [quoted.id]


def test_update_changes_fields(repo: JobRepository) -> None:
    job = repo.create(JobCreate(name="old", message="old", cron="* * * * *"))

    updated = repo.update(
        job.id, JobUpdate(name="new", message="new message", cron="0 8 * * *")
    )

    assert updated is not None
    assert updated.name == "new"
    assert updated.message == "new message"
    assert updated.cron == "0 8 * * *"
    assert updated.updated_at >= job.updated_at


def test_update_unknown_returns_none(repo: JobRepository) -> None:
    assert repo.update("nope", JobUpdate(name="x")) is None


def test_set_enabled_toggles(repo: JobRepository) -> None:
    job = repo.create(JobCreate(name="j", message="m", cron="* * * * *"))

    disabled = repo.set_enabled(job.id, enabled=False)

    assert disabled is not None
    assert disabled.enabled is False


def test_delete(repo: JobRepository) -> None:
    job = repo.create(JobCreate(name="j", message="m", cron="* * * * *"))

    assert repo.delete(job.id) is True
    assert repo.get(job.id) is None
    assert repo.delete(job.id) is False


def test_record_run_persists_status(repo: JobRepository) -> None:
    job = repo.create(JobCreate(name="j", message="m", cron="* * * * *"))
    ran_at = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)

    repo.record_run(job.id, status=JobStatus.ERROR, error="boom", ran_at=ran_at)

    fetched = repo.get(job.id)
    assert fetched is not None
    assert fetched.last_status is JobStatus.ERROR
    assert fetched.last_error == "boom"
    assert fetched.last_run_at == ran_at


def test_set_next_run(repo: JobRepository) -> None:
    job = repo.create(JobCreate(name="j", message="m", cron="* * * * *"))
    next_run = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)

    repo.set_next_run(job.id, next_run)

    fetched = repo.get(job.id)
    assert fetched is not None
    assert fetched.next_run_at == next_run


def test_invalid_cron_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid cron"):
        JobCreate(name="j", message="m", cron="not a cron")


def test_empty_message_rejected() -> None:
    with pytest.raises(ValueError, match="Message must not be empty"):
        JobCreate(name="j", message="   ", cron="* * * * *")
