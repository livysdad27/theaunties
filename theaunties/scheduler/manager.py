"""Scheduler manager — APScheduler setup and topic scheduling."""

import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages scheduled research runs using APScheduler."""

    def __init__(self, run_callback):
        """Initialize the scheduler.

        Args:
            run_callback: Async function to call for each scheduled run.
                          Signature: async def callback(topic_id: int) -> None
        """
        self._scheduler = AsyncIOScheduler()
        self._run_callback = run_callback
        self._jobs: dict[int, str] = {}  # topic_id -> job_id
        self._running = False

    def start(self) -> None:
        """Start the scheduler."""
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info("Scheduler started")

    def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self._running:
            self._scheduler.shutdown()
            self._running = False
            logger.info("Scheduler shut down")

    @property
    def is_running(self) -> bool:
        return self._running

    def add_topic(self, topic_id: int, cron_expression: str) -> str:
        """Schedule a topic for recurring research runs.

        Args:
            topic_id: The topic to schedule.
            cron_expression: Standard 5-field cron expression (minute hour day month weekday).

        Returns:
            The job ID.
        """
        if topic_id in self._jobs:
            self.remove_topic(topic_id)

        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expression!r} (expected 5 fields)")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )

        job = self._scheduler.add_job(
            self._execute_run,
            trigger=trigger,
            args=[topic_id],
            id=f"topic_{topic_id}",
            name=f"Research run for topic {topic_id}",
            replace_existing=True,
        )

        self._jobs[topic_id] = job.id
        logger.info("Scheduled topic %d with cron: %s", topic_id, cron_expression)
        return job.id

    def remove_topic(self, topic_id: int) -> None:
        """Remove a topic from the schedule."""
        job_id = self._jobs.pop(topic_id, None)
        if job_id:
            try:
                self._scheduler.remove_job(job_id)
                logger.info("Removed schedule for topic %d", topic_id)
            except Exception:
                pass  # Job may already be gone

    def get_next_run(self, topic_id: int) -> datetime | None:
        """Get the next scheduled run time for a topic."""
        job_id = self._jobs.get(topic_id)
        if job_id:
            job = self._scheduler.get_job(job_id)
            if job:
                return job.next_run_time
        return None

    def get_scheduled_topics(self) -> list[dict]:
        """Get all scheduled topics with their next run times."""
        result = []
        for topic_id, job_id in self._jobs.items():
            job = self._scheduler.get_job(job_id)
            result.append({
                "topic_id": topic_id,
                "job_id": job_id,
                "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
            })
        return result

    async def trigger_now(self, topic_id: int) -> None:
        """Trigger an immediate research run for a topic."""
        logger.info("Triggering immediate run for topic %d", topic_id)
        await self._execute_run(topic_id)

    async def _execute_run(self, topic_id: int) -> None:
        """Execute a research run (called by the scheduler)."""
        logger.info("Executing scheduled run for topic %d", topic_id)
        try:
            await self._run_callback(topic_id)
        except Exception as e:
            logger.error("Scheduled run failed for topic %d: %s", topic_id, e)
