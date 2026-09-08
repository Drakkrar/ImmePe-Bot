"""HTTP routes for the job dashboard (server-rendered Jinja2 + HTMX).

Handlers read the shared `BotService`, its `JobRepository`, and the templates from
`request.app.state`. Mutating routes update the DB **and** the live scheduler (via the
service) so edits take effect without a restart. Data-returning partials drive HTMX
swaps; validation errors re-render the form partial with a message.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from immepe_bot.models import JobCreate, JobStatus, JobUpdate
from immepe_bot.service import BotService
from immepe_bot.store import JobRepository

router = APIRouter()


def _service(request: Request) -> BotService:
    service: BotService = request.app.state.service
    return service


def _repo(request: Request) -> JobRepository:
    return _service(request).repo


def _templates(request: Request) -> Jinja2Templates:
    templates: Jinja2Templates = request.app.state.templates
    return templates


def _format_validation_error(exc: ValidationError) -> str:
    return "; ".join(f"{error['loc'][-1]}: {error['msg']}" for error in exc.errors())


@router.get("/")
def index(request: Request) -> Response:
    jobs = _repo(request).list()
    return _templates(request).TemplateResponse(request, "index.html", {"jobs": jobs})


@router.get("/jobs")
def list_jobs(request: Request, q: Annotated[str, Query()] = "") -> Response:
    repo = _repo(request)
    jobs = repo.search(q) if q.strip() else repo.list()
    return _templates(request).TemplateResponse(
        request, "partials/job_list.html", {"jobs": jobs}
    )


@router.get("/jobs/new")
def new_job_form(request: Request) -> Response:
    return _templates(request).TemplateResponse(
        request, "partials/job_form.html", {"job": None, "error": None}
    )


@router.get("/jobs/{job_id}/edit")
def edit_job_form(request: Request, job_id: str) -> Response:
    job = _repo(request).get(job_id)
    if job is None:
        return Response(status_code=404)
    return _templates(request).TemplateResponse(
        request, "partials/job_form.html", {"job": job, "error": None}
    )


@router.post("/jobs")
def create_job(
    request: Request,
    name: Annotated[str, Form()],
    message: Annotated[str, Form()],
    cron: Annotated[str, Form()],
    enabled: Annotated[bool, Form()] = False,
) -> Response:
    try:
        data = JobCreate(name=name, message=message, cron=cron, enabled=enabled)
    except ValidationError as exc:
        return _templates(request).TemplateResponse(
            request,
            "partials/job_form.html",
            {"job": None, "error": _format_validation_error(exc)},
            status_code=422,
        )
    job = _repo(request).create(data)
    _service(request).apply_job(job)
    return _templates(request).TemplateResponse(
        request,
        "partials/flash.html",
        {"message": f"Created “{job.name}”.", "level": "success"},
        headers={"HX-Trigger": "jobsChanged"},
    )


@router.post("/jobs/{job_id}")
def update_job(
    request: Request,
    job_id: str,
    name: Annotated[str, Form()],
    message: Annotated[str, Form()],
    cron: Annotated[str, Form()],
    enabled: Annotated[bool, Form()] = False,
) -> Response:
    repo = _repo(request)
    if repo.get(job_id) is None:
        return Response(status_code=404)
    try:
        data = JobUpdate(name=name, message=message, cron=cron, enabled=enabled)
    except ValidationError as exc:
        job = repo.get(job_id)
        return _templates(request).TemplateResponse(
            request,
            "partials/job_form.html",
            {"job": job, "error": _format_validation_error(exc)},
            status_code=422,
        )
    updated = repo.update(job_id, data)
    if updated is None:
        return Response(status_code=404)
    _service(request).apply_job(updated)
    return _templates(request).TemplateResponse(
        request,
        "partials/flash.html",
        {"message": f"Updated “{updated.name}”.", "level": "success"},
        headers={"HX-Trigger": "jobsChanged"},
    )


@router.post("/jobs/{job_id}/toggle")
def toggle_job(request: Request, job_id: str) -> Response:
    repo = _repo(request)
    job = repo.get(job_id)
    if job is None:
        return Response(status_code=404)
    updated = repo.set_enabled(job_id, enabled=not job.enabled)
    if updated is None:
        return Response(status_code=404)
    _service(request).apply_job(updated)
    return _templates(request).TemplateResponse(
        request, "partials/job_list.html", {"jobs": repo.list()}
    )


@router.post("/jobs/{job_id}/delete")
def delete_job(request: Request, job_id: str) -> Response:
    repo = _repo(request)
    if repo.get(job_id) is None:
        return Response(status_code=404)
    _service(request).unschedule_job(job_id)
    repo.delete(job_id)
    return _templates(request).TemplateResponse(
        request, "partials/job_list.html", {"jobs": repo.list()}
    )


@router.post("/jobs/{job_id}/send-now")
async def send_now(request: Request, job_id: str) -> Response:
    repo = _repo(request)
    job = repo.get(job_id)
    if job is None:
        return Response(status_code=404)
    ran_at = datetime.now(tz=UTC)
    try:
        await _service(request).send_message(job.message)
    except Exception as exc:  # surface the failure in the UI instead of crashing
        repo.record_run(job_id, status=JobStatus.ERROR, error=str(exc), ran_at=ran_at)
        return _templates(request).TemplateResponse(
            request,
            "partials/flash.html",
            {"message": f"Send failed: {exc}", "level": "error"},
            status_code=200,
        )
    repo.record_run(job_id, status=JobStatus.SUCCESS, error=None, ran_at=ran_at)
    return _templates(request).TemplateResponse(
        request,
        "partials/flash.html",
        {"message": f"Sent “{job.name}” now.", "level": "success"},
    )


@router.get("/healthz")
def healthz(request: Request) -> JSONResponse:
    # Serving at all implies the startup guard passed and the session was authenticated.
    jobs_count = len(_repo(request).list())
    return JSONResponse({"status": "ok", "jobs_count": jobs_count})
