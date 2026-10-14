"""MySQL 8 durability check for committed agent checkpoint state.

Runs in CI's dedicated MySQL service and must not connect to production DB.
"""
import os
from uuid import uuid4

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_MYSQL_CHECKPOINT_TESTS") != "1",
    reason="Requires dedicated disposable MySQL service",
)
def test_checkpoint_survives_independent_sessions_and_is_idempotent():
    from app.orchestration.checkpoints import (
        load_checkpoint, save_checkpoint, stage_complete,
    )
    from app.storage.database import get_app_engine
    from app.storage.models import AnalystCheckpoint

    engine = get_app_engine()
    AnalystCheckpoint.__table__.create(engine, checkfirst=True)
    run_id = str(uuid4())
    initial = {
        "run_id": run_id, "question": "Revenue by region",
        "full_catalog": [
            {"safe_name": "region", "col_type": "str"},
            {"safe_name": "sales", "col_type": "float"},
        ],
    }
    try:
        save_checkpoint(run_id, "supervisor", initial)
        assert stage_complete(run_id, "supervisor")
        # A new transaction uses database state, not a process-local cache.
        assert load_checkpoint(run_id) == (initial, ["supervisor"])
        save_checkpoint(run_id, "supervisor", {"run_id": run_id, "question": "changed"})
        assert load_checkpoint(run_id) == (initial, ["supervisor"])
        save_checkpoint(run_id, "source_resolver", {**initial, "table_name": "sales"})
        state, stages = load_checkpoint(run_id)
        assert state["table_name"] == "sales"
        assert stages == ["supervisor", "source_resolver"]
    finally:
        with engine.begin() as connection:
            connection.execute(
                AnalystCheckpoint.__table__.delete().where(AnalystCheckpoint.run_id == run_id)
            )
