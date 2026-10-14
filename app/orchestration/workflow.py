"""Temporal workflow: durable coordination, never LLMs, DB access or Pandas.

The existing LangGraph multi-agent graph runs inside an Activity. Only compact,
JSON-serializable job metadata enters Temporal's workflow event history.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.orchestration.activities import (
        execute_agent_team,
        deliver_report,
        profile_source,
        prepare_analysis,
        publish_analysis,
        review_analysis,
    )


@workflow.defn
class AnalystWorkflow:
    """Durable analyst job with explicit independent quality and approval gates."""

    def __init__(self) -> None:
        self._approval: bool | None = None
        self._progress: dict[str, Any] = {
            "status": "queued",
            "stage": "queued",
            "run_id": None,
        }

    @workflow.query
    def progress(self) -> dict[str, Any]:
        return dict(self._progress)

    @workflow.signal
    def approve(self, accepted: bool) -> None:
        """Human review decision; Temporal durably records the signal."""
        self._approval = bool(accepted)

    async def _step(
        self,
        stage: str,
        fn: Any,
        payload: dict[str, Any],
        *,
        timeout: timedelta,
        attempts: int = 3,
        heartbeat_timeout: timedelta | None = None,
    ) -> dict[str, Any]:
        self._progress["status"] = "running"
        self._progress["stage"] = stage
        result = await workflow.execute_activity(
            fn,
            payload,
            start_to_close_timeout=timeout,
            heartbeat_timeout=heartbeat_timeout,
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=30),
                maximum_attempts=attempts,
            ),
        )
        return result

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        run_id = request["run_id"]
        self._progress["run_id"] = run_id

        context = await self._step(
            "source_and_governance", prepare_analysis, request,
            timeout=timedelta(seconds=60),
        )
        profile = await self._step(
            "data_profiling", profile_source, context,
            timeout=timedelta(seconds=60),
        )
        analysis = await self._step(
            "specialist_agents", execute_agent_team, context,
            timeout=timedelta(minutes=30), attempts=2,
            heartbeat_timeout=timedelta(minutes=4),
        )
        # Use independent catalog profiling as the governance source of truth.
        review_input = {**analysis, "pii_columns": profile["pii_columns"],
                        "catalog_present": profile["catalog_present"]}
        review = await self._step(
            "quality_assurance", review_analysis, review_input,
            timeout=timedelta(seconds=30),
        )

        outcome = review["outcome"]
        if outcome == "needs_approval":
            self._progress["status"] = "waiting_for_approval"
            self._progress["stage"] = "human_review"
            self._progress["review_reasons"] = review["reasons"]
            try:
                await workflow.wait_condition(
                    lambda: self._approval is not None,
                    timeout=timedelta(days=3),
                )
                outcome = "approved" if self._approval else "rejected"
            except asyncio.TimeoutError:
                outcome = "expired"

        publication = await self._step(
            "publication", publish_analysis,
            {"run_id": run_id, "outcome": outcome},
            timeout=timedelta(seconds=60),
        )

        report = None
        if outcome == "approved" and context.get("include_report"):
            report = await self._step(
                "stakeholder_report", deliver_report,
                {"run_id": run_id, "format": "pdf"},
                timeout=timedelta(minutes=15), attempts=2,
                heartbeat_timeout=timedelta(minutes=4),
            )

        status = "completed" if outcome == "approved" else outcome
        self._progress.update({"status": status, "stage": "done"})
        return {
            "status": status,
            "run_id": run_id,
            "source_id": context["source_id"],
            "review": review,
            "data_profile": profile,
            "publication": publication,
            "report": report,
        }
