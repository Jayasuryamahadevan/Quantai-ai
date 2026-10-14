"""Integration smoke test against Temporal's ephemeral test server.

Only enabled in CI with RUN_TEMPORAL_TEST_SERVER=1; first run downloads the
Temporal test-server binary. No Ollama/MySQL is required because external
activities are replaced by contracts.
"""
import asyncio
import os

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.orchestration.workflow import AnalystWorkflow


@activity.defn(name="prepare_analysis")
async def fake_prepare(request):
    return {
        "run_id": request["run_id"],
        "source_id": "mock-source",
        "include_report": bool(request.get("include_report")),
    }


@activity.defn(name="profile_source")
async def fake_profile(context):
    return {
        "pii_columns": 0,
        "catalog_present": True,
        "row_count": 100,
        "column_count": 3,
        "types": {"int": 2, "str": 1},
    }


@activity.defn(name="supervise_analysis")
async def fake_supervise(context):
    return {"run_id": context["run_id"], "route": "continue"}


@activity.defn(name="discover_schema")
async def fake_discover(context):
    return {"run_id": context["run_id"], "route": "continue"}


@activity.defn(name="plan_analysis")
async def fake_plan(context):
    return {"run_id": context["run_id"], "route": "continue", "planned": True}


@activity.defn(name="execute_analysis")
async def fake_agents(context):
    return {
        "run_id": context["run_id"],
        "insight_present": True,
        "generated_sql": True,
        "verified": True,
        "confidence": "High",
        "errors": False,
    }


@activity.defn(name="review_analysis")
async def fake_review(context):
    return {"outcome": "approved", "reasons": []}


@activity.defn(name="publish_analysis")
async def fake_publish(request):
    return {"run_id": request["run_id"], "status": "success"}


@activity.defn(name="deliver_report")
async def fake_report(request):
    return {"status": "ready", "format": "pdf"}


@pytest.mark.skipif(not os.getenv("RUN_TEMPORAL_TEST_SERVER"),
                    reason="Set RUN_TEMPORAL_TEST_SERVER=1 to download a Temporal test server")
def test_durable_workflow_runs_on_real_temporal_test_server():
    async def run():
        async with await WorkflowEnvironment.start_time_skipping() as environment:
            async with Worker(
                environment.client,
                task_queue="quantai-tests",
                workflows=[AnalystWorkflow],
                activities=[
                    fake_prepare, fake_profile, fake_supervise, fake_discover,
                    fake_plan, fake_agents, fake_review, fake_publish, fake_report,
                ],
            ):
                result = await environment.client.execute_workflow(
                    AnalystWorkflow.run,
                    {"run_id": "test-run-001", "include_report": True},
                    id="quantai-test-run-001",
                    task_queue="quantai-tests",
                )
                assert result["status"] == "completed"
                assert result["source_id"] == "mock-source"
                assert result["publication"]["status"] == "success"
                assert result["report"]["status"] == "ready"

    asyncio.run(run())
