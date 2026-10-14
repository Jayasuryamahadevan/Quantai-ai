"""Temporal activities (side effects are NEVER executed in workflow code).

Each activity receives only identifiers / small metadata. LangGraph and local
Ollama remain responsible for the specialist agent implementation.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.orchestration.quality import decide_review

log = logging.getLogger(__name__)


def _existing_analysis(run_id: str, question: str, source_id: str) -> dict[str, Any] | None:
    from app.storage.database import app_session
    from app.storage.models import ColumnCatalog, QueryRun
    from sqlalchemy import func, select

    with app_session() as db:
        run = db.get(QueryRun, run_id)
        if run is None:
            return None
        if run.question != question or run.source_id != source_id:
            raise ApplicationError("Idempotency key belongs to another request", non_retryable=True)
        pii_count = db.scalar(
            select(func.count()).select_from(ColumnCatalog)
            .where(ColumnCatalog.source_id == source_id, ColumnCatalog.is_pii.is_(True))
        ) or 0
        quality = (run.timing_ms or {}).get("quality", {})
        return {
            "run_id": run.id,
            "insight_present": bool(run.insight_text and run.insight_text.strip()),
            "generated_sql": bool(run.generated_sql),
            "verified": bool(run.verified),
            "confidence": run.confidence,
            "pii_columns": int(pii_count),
            "fallback_sql": bool(run.is_fallback_sql),
            "errors": bool(run.error_message),
            "clarification_question": quality.get("clarification_question"),
            "grounding_issues": bool(quality.get("grounding_issues")),
            "number_check_valid": quality.get("number_check_valid"),
            "intent": quality.get("intent"),
            "row_count": run.row_count,
        }


@activity.defn
def prepare_analysis(request: dict[str, Any]) -> dict[str, Any]:
    """Resolve a stable source, enforce local ownership of session, and initialize context."""
    from sqlalchemy import select
    from app.storage.database import app_session
    from app.storage.models import ChatSession, Source, QueryRun

    question = str(request["question"]).strip()
    if not question or len(question) > 2000:
        raise ApplicationError("Question must contain 1–2000 characters", non_retryable=True)

    with app_session() as db:
        source_id = request.get("source_id")
        if source_id:
            src = db.get(Source, source_id)
        else:
            src = db.execute(
                select(Source).where(Source.is_active.is_(True))
                .order_by(Source.updated_at.desc()).limit(1)
            ).scalar_one_or_none()
        if src is None or not src.is_active or not src.table_name:
            raise ApplicationError("No active SQL data source is available", non_retryable=True)

        source_id = src.id
        session_id = request["session_id"]
        existing_session = db.get(ChatSession, session_id)
        if existing_session is None:
            db.add(ChatSession(id=session_id, source_id=source_id))
        elif existing_session.source_id not in (None, source_id):
            raise ApplicationError("Session belongs to another data source", non_retryable=True)
        elif existing_session.source_id is None:
            existing_session.source_id = source_id

        prior = request.get("previous_run_id")
        if prior:
            prior_run = db.get(QueryRun, prior)
            if (prior_run is None or prior_run.session_id != session_id
                    or prior_run.source_id != source_id):
                raise ApplicationError("Previous run does not belong to this source/session", non_retryable=True)

    return {
        "run_id": request["run_id"],
        "question": question,
        "session_id": request["session_id"],
        "source_id": source_id,
        "previous_run_id": request.get("previous_run_id"),
        "include_report": bool(request.get("include_report", False)),
    }


def _run_existing_graph(context: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import select
    from app.graph.state import cache_clear, new_state
    from app.graph.workflow import get_workflow
    from app.storage.database import app_session
    from app.storage.models import Message, QueryRun, ColumnCatalog

    run_id = context["run_id"]
    source_id = context["source_id"]

    with app_session() as db:
        history_rows = db.execute(
            select(Message).where(Message.session_id == context["session_id"])
            .order_by(Message.created_at.desc()).limit(6)
        ).scalars().all()
        history = [
            ("User: " if r.role == "user" else "Assistant: ") + r.content[:200]
            for r in reversed(history_rows)
        ]
        previous = db.get(QueryRun, context["previous_run_id"]) if context.get("previous_run_id") else None
        previous_plan = previous.plan_json if previous else None
        pii_count = len(db.execute(
            select(ColumnCatalog.id).where(
                ColumnCatalog.source_id == source_id,
                ColumnCatalog.is_pii.is_(True),
            )
        ).all())

    async def _run() -> dict[str, Any]:
        state = new_state(
            question=context["question"],
            session_id=context["session_id"],
            source_id=source_id,
            chat_history=history,
            previous_plan=previous_plan,
        )
        state["run_id"] = run_id
        async for updates in get_workflow().astream(state):
            for node_name, delta in updates.items():
                if isinstance(delta, dict):
                    state.update(delta)
                activity.heartbeat({"agent": node_name})
        return dict(state)

    activity.heartbeat({"agent": "starting"})
    try:
        state = asyncio.run(_run())
        with app_session() as db:
            existing = db.get(QueryRun, run_id)
            if existing is None:
                db.add(QueryRun(
                    id=run_id,
                    session_id=context["session_id"],
                    source_id=source_id,
                    question=context["question"],
                    plan_json=state.get("query_plan"),
                    generated_sql=state.get("generated_sql"),
                    status="review_pending",
                    confidence=state.get("confidence"),
                    verified=bool(state.get("verified")),
                    row_count=state.get("result_row_count"),
                    columns_used=state.get("result_columns") or [],
                    error_message="; ".join(state.get("errors") or []) or None,
                    resolved_date_range=(state.get("resolved_date_description") or "")[:128] or None,
                    interpretation_text=state.get("interpretation_text"),
                    insight_text=state.get("insight_text"),
                    is_fallback_sql=bool(state.get("is_fallback_sql")),
                    timing_ms={"quality": {
                        "clarification_question": (state.get("clarification_question") or "")[:500] or None,
                        "grounding_issues": bool(state.get("grounding_issues")),
                    }},
                ))

        return {
            "run_id": run_id,
            "insight_present": bool((state.get("insight_text") or "").strip()),
            "generated_sql": bool(state.get("generated_sql")),
            "verified": bool(state.get("verified")),
            "confidence": state.get("confidence"),
            "pii_columns": pii_count,
            "fallback_sql": bool(state.get("is_fallback_sql")),
            "errors": bool(state.get("errors")),
            "clarification_question": (state.get("clarification_question") or "")[:500] or None,
            "grounding_issues": bool(state.get("grounding_issues")),
            "row_count": state.get("result_row_count"),
        }
    finally:
        # Large DataFrames are never included in Temporal event history.
        cache_clear(run_id)


@activity.defn
def profile_source(context: dict[str, Any]) -> dict[str, Any]:
    """Independent data-steward role: inspect metadata without scanning raw rows."""
    from sqlalchemy import select
    from app.storage.database import app_session
    from app.storage.models import Source, ColumnCatalog

    with app_session() as db:
        src = db.get(Source, context["source_id"])
        if src is None or not src.is_active:
            raise ApplicationError("Data source is no longer active", non_retryable=True)
        columns = db.execute(
            select(ColumnCatalog).where(ColumnCatalog.source_id == src.id)
        ).scalars().all()
        types: dict[str, int] = {}
        for col in columns:
            key = col.col_type or "unknown"
            types[key] = types.get(key, 0) + 1
        return {
            "row_count": src.row_count,
            "column_count": len(columns),
            "catalog_present": bool(columns),
            "pii_columns": sum(1 for col in columns if col.is_pii),
            "high_null_columns": sum(
                1 for col in columns if (col.null_pct or 0) > 30
            ),
            "types": types,
        }


@activity.defn
def execute_agent_team(context: dict[str, Any]) -> dict[str, Any]:
    """Execute existing domain specialist agents under one activity boundary.

    Keeping the dependent nodes together prevents sharing process-local
    DataFrames between Temporal workers. Retry after persisted completion is
    idempotent, using the stable run_id.
    """
    prior = _existing_analysis(context["run_id"], context["question"], context["source_id"])
    if prior is not None:
        return prior
    return _run_existing_graph(context)


@activity.defn
def review_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """Independent rule-based verification and governance reviewer."""
    return decide_review(analysis)


@activity.defn
def publish_analysis(request: dict[str, Any]) -> dict[str, Any]:
    """Idempotently finalize metadata and publish approved chat messages."""
    from sqlalchemy import select
    from app.storage.database import app_session
    from app.storage.models import AnalystCheckpoint, Message, QueryRun

    outcome = request["outcome"]
    statuses = {
        "approved": "success",
        "rejected": "rejected",
        "expired": "expired",
        "needs_clarification": "ambiguous",
    }
    if outcome not in statuses:
        raise ApplicationError("Unsupported review result", non_retryable=True)

    status = statuses[outcome]
    with app_session() as db:
        run = db.get(QueryRun, request["run_id"])
        if run is None:
            raise ApplicationError("Analysis result not found", non_retryable=True)
        if run.status not in ("review_pending", status):
            raise ApplicationError("Analysis already finalized differently", non_retryable=True)

        run.status = status
        if status == "success" and run.session_id:
            already_published = db.execute(
                select(Message.id).where(
                    Message.run_id == run.id,
                    Message.role == "assistant",
                ).limit(1)
            ).first()
            if already_published is None:
                db.add_all([
                    Message(session_id=run.session_id, role="user",
                            content=run.question, run_id=run.id),
                    Message(session_id=run.session_id, role="assistant",
                            content=run.insight_text or "", run_id=run.id),
                ])
        # Privacy: no further specialist replay is required after the final
        # publication decision. Retain only limited quality metadata on QueryRun.
        checkpoint = db.get(AnalystCheckpoint, run.id)
        if checkpoint is not None:
            db.delete(checkpoint)
    return {"run_id":request["run_id"],"status":status,
            "history_path":f"/api/history/{request['run_id']}"}



@activity.defn
def deliver_report(request: dict[str, Any]) -> dict[str, Any]:
    """Generate a report after approval, persisting an idempotent export record.

    Export files live in the app's configured local exports directory. Deploy a
    shared artifact store before running workers on separate hosts.
    """
    from pathlib import Path
    from sqlalchemy import select
    from app.config import get_settings
    from app.export.router import handle_export
    from app.orchestration.report_store import approved_report_path
    from app.storage.database import app_session
    from app.storage.models import Export, QueryRun

    run_id = request["run_id"]
    output_format = request.get("format", "pdf")
    if output_format != "pdf":
        raise ApplicationError("The durable report activity supports PDF only", non_retryable=True)

    with app_session() as db:
        run = db.get(QueryRun, run_id)
        if run is None or run.status != "success":
            raise ApplicationError("Cannot export an unpublished analysis", non_retryable=True)
        if not run.generated_sql:
            return {"status": "skipped", "reason": "No tabular SQL result to export"}
        previous = db.execute(
            select(Export).where(
                Export.run_id == run_id, Export.format == output_format
            ).order_by(Export.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if previous:
            try:
                approved_report_path(previous.file_path, get_settings().exports_dir)
            except (ValueError, OSError) as exc:
                # Never silently regenerate a recorded artifact from mutable source data.
                raise ApplicationError("Recorded report artifact is missing or invalid", non_retryable=True) from exc
            return {
                "status": "ready",
                "format": output_format,
                "download_url": f"/api/analysis/jobs/reports/{run_id}",
            }

    activity.heartbeat({"role": "report_author", "phase": "generating"})
    response = asyncio.run(handle_export(run_id, output_format))
    report_file = approved_report_path(str(response.path), get_settings().exports_dir)

    with app_session() as db:
        latest = db.execute(
            select(Export).where(
                Export.run_id == run_id, Export.format == output_format
            ).limit(1)
        ).scalar_one_or_none()
        if latest is None:
            db.add(Export(
                run_id=run_id,
                format=output_format,
                file_path=str(report_file),
                file_size_bytes=report_file.stat().st_size,
            ))

    activity.heartbeat({"role": "report_author", "phase": "saved"})
    return {
        "status": "ready",
        "format": output_format,
        "download_url": f"/api/analysis/jobs/reports/{run_id}",
    }
