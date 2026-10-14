"""Replay and checkpoint tests without MySQL/Ollama dependencies."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.orchestration.checkpoints import (
    MAX_CHECKPOINT_BYTES, _json_state, load_checkpoint, save_checkpoint,
    stage_complete, checkpoint_progress,
)
from app.storage.models import AnalystCheckpoint


@pytest.fixture
def memory_store(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    AnalystCheckpoint.__table__.create(engine)

    @contextmanager
    def session():
        with Session(engine) as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    monkeypatch.setattr("app.storage.database.app_session", session)
    yield
    engine.dispose()


def test_checkpoint_persists_and_recovers_state(memory_store):
    state = {"run_id": "run-1", "question": "Revenue by region", "intent": "data_query"}
    save_checkpoint("run-1", "supervisor", state)
    assert stage_complete("run-1", "supervisor")
    restored, stages = load_checkpoint("run-1")
    assert stages == ["supervisor"]
    assert restored["question"] == state["question"]
    restored["intent"] = "data_summary"
    save_checkpoint("run-1", "source_resolver", restored)
    assert checkpoint_progress("run-1")["completed_agents"] == [
        "supervisor", "source_resolver",
    ]


def test_stage_retry_does_not_overwrite_a_committed_checkpoint(memory_store):
    initial = {"run_id": "run-2", "question": "First output"}
    save_checkpoint("run-2", "supervisor", initial)
    save_checkpoint("run-2", "supervisor", {"run_id": "run-2", "question": "retry"})
    assert load_checkpoint("run-2") == (initial, ["supervisor"])


def test_wrong_run_id_is_rejected(memory_store):
    with pytest.raises(Exception, match="mismatch"):
        save_checkpoint("correct", "supervisor", {"run_id": "other"})


def test_frames_and_oversized_checkpoints_cannot_enter_temporal_state():
    class LargeFrame:
        pass

    with pytest.raises(TypeError):
        _json_state({"run_id": "run", "result_df": LargeFrame()})
    with pytest.raises(Exception, match="exceeds"):
        _json_state({"run_id": "run", "question": "a" * (MAX_CHECKPOINT_BYTES + 20)})
