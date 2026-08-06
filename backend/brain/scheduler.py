from __future__ import annotations

import asyncio

from .config import enabled, interval_seconds, jobs_enabled
from .jobs import run_job_pipeline
from .service import run_partnership_pipeline


async def brain_scheduler_loop() -> None:
    """Bounded worker loop. Failures are contained and the product API remains available."""
    await asyncio.sleep(45)
    while True:
        try:
            if enabled():
                await asyncio.to_thread(run_partnership_pipeline)
                if jobs_enabled():
                    await asyncio.to_thread(run_job_pipeline)
            await asyncio.sleep(interval_seconds())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("[noytrix_brain] scheduler error:", str(exc)[:250])
            await asyncio.sleep(300)
