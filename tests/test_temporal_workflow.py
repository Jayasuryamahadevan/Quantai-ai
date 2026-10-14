"""Workflow state-machine tests without an external Temporal cluster."""
import asyncio

from app.orchestration import workflow as wf


def _activities(monkeypatch, outcome):
    stages = []

    async def execute(fn, payload, **kwargs):
        stages.append(fn.__name__)
        if fn.__name__ == "prepare_analysis":
            return {"run_id": "run1", "source_id": "source1"}
        if fn.__name__ == "profile_source":
            return {"pii_columns": 0, "catalog_present": True}
        if fn.__name__ == "execute_agent_team":
            return {"run_id": "run1", "insight_present": True}
        if fn.__name__ == "review_analysis":
            return {"outcome": outcome, "reasons": [] if outcome == "approved" else ["Needs verification"]}
        if fn.__name__ == "deliver_report":
            return {"status": "ready", "format": "pdf", "download_url": "/api/export/run1?format=pdf"}
        if fn.__name__ == "publish_analysis":
            return {"run_id": "run1", "status": payload["outcome"]}
        raise AssertionError("Unexpected activity")

    monkeypatch.setattr(wf.workflow, "execute_activity", execute)
    return stages


def test_verified_job_runs_activities_in_order(monkeypatch):
    stages = _activities(monkeypatch, "approved")

    async def run():
        instance = wf.AnalystWorkflow()
        result = await instance.run({"run_id": "run1"})
        assert result["status"] == "completed"
        assert instance.progress()["stage"] == "done"

    asyncio.run(run())
    assert stages == [
        "prepare_analysis", "profile_source", "execute_agent_team",
        "review_analysis", "publish_analysis",
    ]


def test_human_review_signal_is_honored(monkeypatch):
    stages = _activities(monkeypatch, "needs_approval")

    async def wait_condition(predicate, timeout):
        for _ in range(50):
            if predicate():
                return
            await asyncio.sleep(0)
        raise AssertionError("Human approval was not processed")

    monkeypatch.setattr(wf.workflow, "wait_condition", wait_condition)

    async def run():
        instance = wf.AnalystWorkflow()
        task = asyncio.create_task(instance.run({"run_id": "run1"}))
        for _ in range(50):
            if instance.progress()["status"] == "waiting_for_approval":
                break
            await asyncio.sleep(0)
        assert instance.progress()["status"] == "waiting_for_approval"
        instance.approve(True)
        result = await task
        assert result["status"] == "completed"

    asyncio.run(run())
    assert stages[-1] == "publish_analysis"


def test_rejected_result_is_not_auto_published_as_success(monkeypatch):
    _activities(monkeypatch, "rejected")

    async def run():
        instance = wf.AnalystWorkflow()
        result = await instance.run({"run_id": "run1"})
        assert result["status"] == "rejected"

    asyncio.run(run())
