from collections.abc import Iterator
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi.testclient import TestClient

from immepe_bot.config import Settings
from immepe_bot.models import JobCreate
from immepe_bot.service import BotService
from immepe_bot.store import JobRepository
from immepe_bot.web.app import build_app
from immepe_bot.whatsapp import WhatsAppClient


@pytest.fixture
def whatsapp_mock() -> MagicMock:
    client = MagicMock(spec=WhatsAppClient)
    client.open_self_chat = AsyncMock()
    client.send = AsyncMock()
    return client


@pytest.fixture
def service(repo: JobRepository, whatsapp_mock: MagicMock) -> BotService:
    return BotService(
        settings=Settings(),
        repo=repo,
        scheduler=AsyncIOScheduler(),
        client=cast(WhatsAppClient, whatsapp_mock),
    )


@pytest.fixture
def client(service: BotService) -> Iterator[TestClient]:
    app = build_app(Settings(), service=service)
    with TestClient(app) as test_client:
        yield test_client


def test_index_renders(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "ImmePe-Bot" in response.text


def test_create_job_persists_and_schedules(
    client: TestClient, service: BotService
) -> None:
    response = client.post(
        "/jobs",
        data={
            "name": "Timesheet",
            "message": "Fill the timesheet",
            "cron": "0 9 * * 1-5",
            "enabled": "true",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "jobsChanged"
    jobs = service.repo.list()
    assert len(jobs) == 1
    assert service.scheduler.get_job(jobs[0].id) is not None


def test_create_job_invalid_cron_returns_form(
    client: TestClient, service: BotService
) -> None:
    response = client.post(
        "/jobs",
        data={"name": "x", "message": "y", "cron": "nope", "enabled": "true"},
    )

    assert response.status_code == 422
    assert "Invalid cron" in response.text
    assert service.repo.list() == []


def test_toggle_job_unschedules_when_disabled(
    client: TestClient, service: BotService
) -> None:
    job = service.repo.create(JobCreate(name="j", message="m", cron="* * * * *"))
    service.apply_job(job)

    response = client.post(f"/jobs/{job.id}/toggle")

    assert response.status_code == 200
    updated = service.repo.get(job.id)
    assert updated is not None
    assert updated.enabled is False
    assert service.scheduler.get_job(job.id) is None


def test_delete_job(client: TestClient, service: BotService) -> None:
    job = service.repo.create(JobCreate(name="j", message="m", cron="* * * * *"))
    service.apply_job(job)

    response = client.post(f"/jobs/{job.id}/delete")

    assert response.status_code == 200
    assert service.repo.get(job.id) is None
    assert service.scheduler.get_job(job.id) is None


def test_send_now_calls_send(
    client: TestClient, service: BotService, whatsapp_mock: MagicMock
) -> None:
    job = service.repo.create(JobCreate(name="Ping", message="Hello", cron="* * * * *"))

    response = client.post(f"/jobs/{job.id}/send-now")

    assert response.status_code == 200
    assert "Sent" in response.text
    whatsapp_mock.send.assert_awaited_once_with("Hello")
    recorded = service.repo.get(job.id)
    assert recorded is not None
    assert recorded.last_status is not None


def test_search_filters(client: TestClient, service: BotService) -> None:
    service.repo.create(JobCreate(name="Standup", message="m", cron="* * * * *"))
    service.repo.create(JobCreate(name="Other", message="nothing", cron="* * * * *"))

    response = client.get("/jobs", params={"q": "standup"})

    assert response.status_code == 200
    assert "Standup" in response.text
    assert "Other" not in response.text


def test_healthz(client: TestClient, service: BotService) -> None:
    service.repo.create(JobCreate(name="j", message="m", cron="* * * * *"))

    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["jobs_count"] == 1
