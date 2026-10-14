"""MySQL-backed replay checkpoints shared by Temporal worker processes.

Every stage stores small JSON metadata only. A completed stage is read from
storage on retry; slow LLM calls are not repeated after an acknowledged commit.
This is not a replacement for a versioned tabular result-artifact store.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from temporalio.exceptions import ApplicationError

MAX_CHECKPOINT_BYTES = 2 * 1024 * 1024


def _default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Unsupported checkpoint value type: {type(value).__name__}")


def _json_state(state: dict[str, Any]) -> dict[str, Any]:
    # All DataFrames are held in the execution activity, never checkpointed.
    payload = json.dumps(state, default=_default, allow_nan=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_CHECKPOINT_BYTES:
        raise ApplicationError(
            "Analysis checkpoint exceeds 2 MB; reduce catalog size",
            non_retryable=True,
        )
    return json.loads(payload)


def load_checkpoint(run_id: str) -> tuple[dict[str, Any], list[str]]:
    from app.storage.database import app_session
    from app.storage.models import AnalystCheckpoint

    with app_session() as session:
        row = session.get(AnalystCheckpoint, run_id)
        if row is None:
            return {}, []
        return dict(row.state_json or {}), list(row.completed_stages or [])


def stage_complete(run_id: str, stage: str) -> bool:
    _, completed = load_checkpoint(run_id)
    return stage in completed


def save_checkpoint(run_id: str, stage: str, state: dict[str, Any]) -> None:
    from app.storage.database import app_session
    from app.storage.models import AnalystCheckpoint

    sanitized = _json_state(state)
    if sanitized.get("run_id") != run_id:
        raise ApplicationError("Checkpoint run_id mismatch", non_retryable=True)

    with app_session() as session:
        row = session.execute(
            select(AnalystCheckpoint).where(AnalystCheckpoint.run_id == run_id).with_for_update()
        ).scalar_one_or_none()
        if row is None:
            row = AnalystCheckpoint(run_id=run_id, completed_stages=[], state_json={})
            session.add(row)
        stages = list(row.completed_stages or [])
        if stage not in stages:
            stages.append(stage)
            row.completed_stages = stages
            row.state_json = sanitized


def checkpoint_progress(run_id: str) -> dict[str, Any]:
    state, stages = load_checkpoint(run_id)
    return {
        "run_id": run_id,
        "completed_agents": stages,
        "last_agent": stages[-1] if stages else None,
        "warnings": len(state.get("warnings") or []),
        "errors": len(state.get("errors") or []),
    }
