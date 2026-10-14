"""Temporal-backed analysis job endpoints (disabled unless explicitly enabled).

Local-only API: deploying for multiple users requires authentication,
authorization, source ownership and rate limits first.
"""
from __future__ import annotations

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.config import get_settings
from app.orchestration.workflow import AnalystWorkflow

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis/jobs", tags=["analysis-jobs"])


class AnalysisJobRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    source_id: UUID | None = None
    session_id: UUID | None = None
    previous_run_id: UUID | None = None
    idempotency_key: UUID | None = None
    include_report: bool = False


class ReviewDecision(BaseModel):
    approved: bool


async def _client(request: Request) -> Client:
    cfg = get_settings()
    if not cfg.temporal_enabled:
        raise HTTPException(503, "Durable analysis is disabled; set TEMPORAL_ENABLED=true")
    client = getattr(request.app.state, "temporal_client", None)
    if client is not None:
        return client
    try:
        client = await Client.connect(cfg.temporal_address, namespace=cfg.temporal_namespace)
    except Exception as exc:
        log.warning("Temporal connection unavailable: %s", type(exc).__name__)
        raise HTTPException(503, "Temporal service is unavailable") from exc
    request.app.state.temporal_client = client
    return client


def _handle(client: Client, job_id: str):
    if not job_id.startswith("quantai-analysis-"):
        raise HTTPException(400, "Invalid analysis job ID")
    try:
        UUID(job_id.removeprefix("quantai-analysis-"))
    except ValueError as exc:
        raise HTTPException(400, "Invalid analysis job ID") from exc
    return client.get_workflow_handle(job_id)


@router.post("", status_code=202)
async def start_job(payload: AnalysisJobRequest, request: Request):
    cfg = get_settings()
    client = await _client(request)
    run_id = str(payload.idempotency_key or uuid4())
    workflow_id = f"quantai-analysis-{run_id}"
    message = {
        "run_id": run_id,
        "session_id": str(payload.session_id or uuid4()),
        "question": payload.question.strip(),
        "source_id": str(payload.source_id) if payload.source_id else None,
        "previous_run_id": str(payload.previous_run_id) if payload.previous_run_id else None,
        "include_report": payload.include_report,
    }
    if not message["question"]:
        raise HTTPException(422, "Question must not be blank")
    try:
        await client.start_workflow(
            AnalystWorkflow.run,
            message,
            id=workflow_id,
            task_queue=cfg.temporal_task_queue,
        )
    except WorkflowAlreadyStartedError as exc:
        raise HTTPException(409, "A job already uses this idempotency key") from exc
    except Exception as exc:
        log.exception("Failed to submit Temporal analysis job")
        raise HTTPException(503, "Unable to queue the analysis job") from exc

    return {
        "job_id": workflow_id,
        "run_id": run_id,
        "status": "queued",
        "status_url": f"/api/analysis/jobs/{workflow_id}",
    }


@router.get("/reports/{run_id}")
async def get_approved_report(run_id: UUID, request: Request):
    """Serve the exact approved PDF artifact, never re-execute its SQL."""
    from sqlalchemy import select

    from app.orchestration.report_store import approved_report_path
    from app.storage.database import app_session
    from app.storage.models import Export, QueryRun

    # The durable API is disabled by default and restricted to trusted local use.
    await _client(request)
    run_key = str(run_id)
    with app_session() as db:
        run = db.get(QueryRun, run_key)
        if run is None or run.status != "success":
            raise HTTPException(404, "Approved report not found")
        artifact = db.execute(
            select(Export.file_path)
            .where(Export.run_id == run_key, Export.format == "pdf")
            .order_by(Export.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(404, "Approved report not found")
    try:
        report_path = approved_report_path(artifact, get_settings().exports_dir)
    except (ValueError, OSError) as exc:
        log.warning("Approved report artifact missing or invalid for run %s", run_key)
        raise HTTPException(404, "Approved report artifact not found") from exc

    return FileResponse(
        report_path,
        filename=f"quantai_approved_{run_key}.pdf",
        media_type="application/pdf",
    )


@router.get("/{job_id}")
async def get_job(job_id: str, request: Request):
    client = await _client(request)
    handle = _handle(client, job_id)
    try:
        description = await handle.describe()
    except Exception as exc:
        raise HTTPException(404, "Analysis job not found") from exc
    execution_status = description.status.name.lower()
    if execution_status == "completed":
        try:
            result = await handle.result()
            return {"job_id": job_id, "execution_status": execution_status, **result}
        except Exception as exc:
            log.error("Completed workflow result unavailable: %s", type(exc).__name__)
            raise HTTPException(503, "Job result temporarily unavailable") from exc
    if execution_status != "running":
        return {"job_id": job_id, "status": execution_status}
    try:
        progress = await handle.query(AnalystWorkflow.progress)
    except Exception as exc:
        log.warning("Workflow progress unavailable: %s", type(exc).__name__)
        progress = {"status": "running", "stage": "unknown"}
    return {"job_id": job_id, "execution_status": execution_status, **progress}


@router.post("/{job_id}/review", status_code=202)
async def review_job(job_id: str, payload: ReviewDecision, request: Request):
    client = await _client(request)
    handle = _handle(client, job_id)
    try:
        status = await handle.query(AnalystWorkflow.progress)
        if status.get("status") != "waiting_for_approval":
            raise HTTPException(409, "Job is not waiting for approval")
        await handle.signal(AnalystWorkflow.approve, payload.approved)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(404, "Job unavailable for review") from exc
    return {"job_id": job_id, "decision": "approved" if payload.approved else "rejected"}


@router.post("/{job_id}/cancel", status_code=202)
async def cancel_job(job_id: str, request: Request):
    client = await _client(request)
    handle = _handle(client, job_id)
    try:
        await handle.cancel()
    except Exception as exc:
        raise HTTPException(404, "Cannot cancel job") from exc
    return {"job_id": job_id, "status": "cancellation_requested"}
