"""Role-level resume tests: agent state lives in the checkpoint, not event history."""
import asyncio

from app.orchestration import specialists as roles


def _in_memory_checkpoints(monkeypatch):
    checkpoints = {}
    calls = []

    def load(run_id):
        state, stages = checkpoints.get(run_id, ({}, []))
        return dict(state), list(stages)

    def save(run_id, stage, state):
        _, stages = load(run_id)
        if stage not in stages:
            calls.append(stage)
            checkpoints[run_id] = (dict(state), stages + [stage])

    monkeypatch.setattr(roles, "load_checkpoint", load)
    monkeypatch.setattr(roles, "save_checkpoint", save)
    return checkpoints, calls


def test_supervisor_retries_reuse_committed_state(monkeypatch):
    _, calls = _in_memory_checkpoints(monkeypatch)
    invocations = [0]

    async def classify(context):
        invocations[0] += 1
        return {
            "run_id": context["run_id"], "question": context["question"],
            "intent": "data_query", "errors": [], "clarification_question": None,
        }

    monkeypatch.setattr(roles, "_supervise", classify)
    context = {"run_id": "test-run", "question": "Revenue"}
    assert roles.supervise_analysis(context)["route"] == "continue"
    assert roles.supervise_analysis(context)["route"] == "continue"
    assert invocations == [1]
    assert calls == ["supervisor"]


def test_clarification_short_circuits_downstream_agents(monkeypatch):
    _, calls = _in_memory_checkpoints(monkeypatch)

    async def classify(context):
        return {
            "run_id": context["run_id"],
            "clarification_question": "Which revenue column?",
            "errors": [], "intent": "clarification_needed",
        }

    async def must_not_run(*args):
        raise AssertionError("Unnecessary planner work")

    monkeypatch.setattr(roles, "_supervise", classify)
    monkeypatch.setattr(roles, "_plan", must_not_run)
    context = {"run_id": "clarify"}
    assert roles.supervise_analysis(context)["route"] == "clarification"
    assert roles.discover_schema(context)["route"] == "clarification"
    assert roles.plan_analysis(context)["route"] == "clarification"
    assert calls == ["supervisor", "source_resolver", "query_planner"]


def test_independent_planner_checkpoint_is_resumable(monkeypatch):
    _, calls = _in_memory_checkpoints(monkeypatch)

    async def classify(context):
        return {
            "run_id": context["run_id"], "intent": "data_query",
            "errors": [], "clarification_question": None,
        }

    async def discover(state, func, name):
        assert name == "source_resolver"
        state["full_catalog"] = [{"safe_name": "sales"}]

    invocations = [0]

    async def plan(state):
        invocations[0] += 1
        state["query_plan"] = {"metrics": [{"column": "sales", "agg": "sum"}]}

    monkeypatch.setattr(roles, "_supervise", classify)
    monkeypatch.setattr(roles, "_run_node", discover)
    monkeypatch.setattr(roles, "_plan", plan)
    context = {"run_id": "planning"}
    roles.supervise_analysis(context)
    roles.discover_schema(context)
    assert roles.plan_analysis(context)["planned"] is True
    assert roles.plan_analysis(context)["planned"] is True
    assert invocations == [1]
    assert calls == ["supervisor", "source_resolver", "query_planner"]
