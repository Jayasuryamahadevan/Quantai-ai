"""Stage-level, replay-safe specialist activities for analyst workflows.

A Temporal activity corresponds to one recoverable analyst responsibility:
brief/intent, source discovery, semantic planning and controlled execution.
Every role boundary is checkpointed to SQL; bulky DataFrames remain private
to execution activity. Side effects never occur in workflow code.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.orchestration.checkpoints import load_checkpoint, save_checkpoint

Role = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def _run_node(state: dict[str, Any], role: Role, name: str) -> None:
    activity.heartbeat({"agent": name})
    delta = await role(state)
    if not isinstance(delta, dict):
        raise ApplicationError(f"{name} returned an invalid state update", non_retryable=True)
    state.update(delta)
    activity.heartbeat({"agent": name, "status": "completed"})


def _load_required(run_id: str, required_stage: str) -> dict[str, Any]:
    state, completed = load_checkpoint(run_id)
    if required_stage not in completed:
        raise ApplicationError(
            f"Prerequisite specialist stage {required_stage} has not completed",
            non_retryable=True,
        )
    return state


def _is_blocked(state: dict[str, Any]) -> bool:
    return bool(state.get("errors") or state.get("clarification_question"))


def _route(state: dict[str, Any]) -> str:
    if state.get("errors"):
        return "error"
    if state.get("clarification_question"):
        return "clarification"
    return "continue"


def _history_context(context: dict[str, Any]) -> tuple[list[str], dict[str, Any] | None]:
    from sqlalchemy import select
    from app.storage.database import app_session
    from app.storage.models import Message, QueryRun

    with app_session() as session:
        messages = session.execute(
            select(Message).where(Message.session_id == context["session_id"])
            .order_by(Message.created_at.desc()).limit(6)
        ).scalars().all()
        previous = (
            session.get(QueryRun, context["previous_run_id"])
            if context.get("previous_run_id") else None
        )
        history = [
            ("User: " if item.role == "user" else "Assistant: ") + item.content[:200]
            for item in reversed(messages)
        ]
        return history, previous.plan_json if previous else None


async def _supervise(context: dict[str, Any]) -> dict[str, Any]:
    from app.agents.supervisor import supervisor_node
    from app.graph.state import new_state

    history, previous_plan = _history_context(context)
    state = dict(new_state(
        question=context["question"],
        session_id=context["session_id"],
        source_id=context["source_id"],
        chat_history=history,
        previous_plan=previous_plan,
    ))
    state["run_id"] = context["run_id"]
    await _run_node(state, supervisor_node, "supervisor")
    return state


@activity.defn
def supervise_analysis(context: dict[str, Any]) -> dict[str, Any]:
    """Business analyst: classify intent, resolve follow-up or ask for clarification."""
    run_id = context["run_id"]
    if "supervisor" not in load_checkpoint(run_id)[1]:
        state = asyncio.run(_supervise(context))
        save_checkpoint(run_id, "supervisor", state)
    state, _ = load_checkpoint(run_id)
    return {"run_id": run_id, "agent": "supervisor", "route": _route(state)}


@activity.defn
def discover_schema(context: dict[str, Any]) -> dict[str, Any]:
    """Data engineer/steward: resolve trusted dataset and schema catalog."""
    run_id = context["run_id"]
    state = _load_required(run_id, "supervisor")
    if "source_resolver" not in load_checkpoint(run_id)[1]:
        if not _is_blocked(state):
            from app.agents.source_resolver import source_resolver_node
            asyncio.run(_run_node(state, source_resolver_node, "source_resolver"))
        save_checkpoint(run_id, "source_resolver", state)
    state, _ = load_checkpoint(run_id)
    return {"run_id": run_id, "agent": "source_resolver", "route": _route(state)}


async def _plan(state: dict[str, Any]) -> None:
    from app.agents.sql_generator import column_selector_node, query_planner_node

    intent = state.get("intent")
    if intent == "data_summary":
        return
    if intent == "data_overview":
        # The overview agent needs the complete catalog, not an LLM query plan.
        return
    await _run_node(state, column_selector_node, "column_selector")
    await _run_node(state, query_planner_node, "query_planner")


@activity.defn
def plan_analysis(context: dict[str, Any]) -> dict[str, Any]:
    """Semantic analyst: select relevant columns and develop a grounded query plan."""
    run_id = context["run_id"]
    state = _load_required(run_id, "source_resolver")
    if "query_planner" not in load_checkpoint(run_id)[1]:
        if not _is_blocked(state):
            asyncio.run(_plan(state))
        save_checkpoint(run_id, "query_planner", state)
    state, _ = load_checkpoint(run_id)
    return {
        "run_id": run_id,
        "agent": "query_planner",
        "route": _route(state),
        "intent": state.get("intent"),
        "planned": bool(state.get("query_plan")),
    }


async def _execute(state: dict[str, Any]) -> None:
    from app.agents.data_summary import data_summary_node
    from app.graph.workflow import data_overview_node, confidence_node
    from app.agents.sql_generator import (
        sql_compile_node, validate_and_execute_node,
    )
    from app.graph.workflow import retry_sql_node, cross_check_node
    from app.agents.cleaner import cleaner_node
    from app.agents.stats_analyzer import stats_analyzer_node
    from app.agents.visualizer import visualizer_node
    from app.agents.insight import insight_node
    from app.config import get_settings

    if _is_blocked(state):
        return

    intent = state.get("intent")
    if intent == "data_summary":
        await _run_node(state, data_summary_node, "data_summary")
        return
    if intent == "data_overview":
        await _run_node(state, data_overview_node, "data_overview")
        return

    # SQL author, constrained executor, verification and repair loop.
    max_repairs = 2
    await _run_node(state, sql_compile_node, "sql_compile")
    while True:
        await _run_node(state, validate_and_execute_node, "validate_execute")
        validated = (state.get("validation_result") or {}).get("valid") is True
        retries = state.get("retry_count") or 0
        if not validated:
            if retries >= max_repairs:
                state["errors"] = list(state.get("errors") or []) + [
                    "SQL validation or execution failed after the retry budget."
                ]
                break
            await _run_node(state, retry_sql_node, "retry_sql")
            await _run_node(state, sql_compile_node, "sql_compile")
            continue
        await _run_node(state, cross_check_node, "cross_check")
        cross = state.get("cross_check_result") or {}
        if (
            cross.get("verified") is False
            and get_settings().accuracy_mode in ("balanced", "max")
            and retries < max_repairs
        ):
            await _run_node(state, retry_sql_node, "retry_sql")
            await _run_node(state, sql_compile_node, "sql_compile")
            continue
        break

    if not (state.get("validation_result") or {}).get("valid"):
        return
    for role, name in (
        (cleaner_node, "cleaner"),
        (stats_analyzer_node, "stats_analyzer"),
        (visualizer_node, "visualizer"),
        (insight_node, "insight"),
        (confidence_node, "confidence"),
    ):
        await _run_node(state, role, name)


def _persist_final(context: dict[str, Any], state: dict[str, Any]) -> None:
    from app.storage.database import app_session
    from app.storage.models import QueryRun

    with app_session() as session:
        prior = session.get(QueryRun, context["run_id"])
        if prior is not None:
            if (
                prior.question != context["question"]
                or prior.source_id != context["source_id"]
                or prior.session_id != context["session_id"]
            ):
                raise ApplicationError("Run ID collision", non_retryable=True)
            return
        raw_trace = state.get("trace") or []
        session.add(QueryRun(
            id=context["run_id"],
            session_id=context["session_id"],
            source_id=context["source_id"],
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
                "number_check_valid": (state.get("number_check_result") or {}).get("valid"),
                "trace_steps": [r.get("step") for r in raw_trace if isinstance(r, dict)][:40],
                "intent": state.get("intent"),
            }},
        ))


@activity.defn
def execute_analysis(context: dict[str, Any]) -> dict[str, Any]:
    """SQL, statistics, chart and narrative specialists.

    These steps share one activity until a distributed, versioned DataFrame
    store is available; this is the only area requiring process-local cache.
    """
    from app.graph.state import cache_clear
    from app.orchestration.activities import _existing_analysis

    run_id = context["run_id"]
    existing = _existing_analysis(run_id, context["question"], context["source_id"])
    if existing is not None:
        return existing
    state = _load_required(run_id, "query_planner")
    try:
        activity.heartbeat({"agent": "analysis_start"})
        asyncio.run(_execute(state))
        _persist_final(context, state)
        result = _existing_analysis(run_id, context["question"], context["source_id"])
        if result is None:
            raise RuntimeError("Final run was not persisted")
        return result
    finally:
        cache_clear(run_id)
