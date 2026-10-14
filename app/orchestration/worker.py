"""Run separately: python -m app.orchestration.worker"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from app.config import get_settings
from app.orchestration.activities import (
    deliver_report, execute_agent_team, prepare_analysis, profile_source, publish_analysis, review_analysis,
)
from app.orchestration.workflow import AnalystWorkflow


async def main() -> None:
    cfg = get_settings()
    logging.basicConfig(level=logging.INFO)
    client = await Client.connect(cfg.temporal_address, namespace=cfg.temporal_namespace)
    with ThreadPoolExecutor(
        max_workers=cfg.temporal_max_concurrent_activities,
        thread_name_prefix="quantai-agent",
    ) as executor:
        worker = Worker(
            client,
            task_queue=cfg.temporal_task_queue,
            workflows=[AnalystWorkflow],
            activities=[
                prepare_analysis, profile_source, execute_agent_team,
                review_analysis, publish_analysis, deliver_report,
            ],
            activity_executor=executor,
            max_concurrent_activities=cfg.temporal_max_concurrent_activities,
        )
        logging.getLogger(__name__).info(
            "Temporal worker connected: %s / %s",
            cfg.temporal_namespace, cfg.temporal_task_queue,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
