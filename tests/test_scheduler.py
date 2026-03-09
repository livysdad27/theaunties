"""Tests for the scheduler manager."""

import pytest

from theaunties.scheduler.manager import SchedulerManager


@pytest.fixture
def run_log():
    """Track which topic IDs have been run."""
    return []


@pytest.fixture
async def scheduler(run_log):
    """Create a scheduler with a logging callback (needs event loop)."""
    async def callback(topic_id: int):
        run_log.append(topic_id)

    mgr = SchedulerManager(run_callback=callback)
    mgr.start()
    yield mgr
    mgr.shutdown()


class TestSchedulerLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_shutdown(self, run_log):
        async def noop(tid): pass
        mgr = SchedulerManager(run_callback=noop)
        assert not mgr.is_running
        mgr.start()
        assert mgr.is_running
        mgr.shutdown()
        assert not mgr.is_running

    @pytest.mark.asyncio
    async def test_double_start(self, scheduler):
        """Starting an already running scheduler should be safe."""
        scheduler.start()  # Already started by fixture
        assert scheduler.is_running


class TestTopicScheduling:
    @pytest.mark.asyncio
    async def test_add_topic(self, scheduler):
        """Should add a job for a topic."""
        job_id = scheduler.add_topic(1, "0 6 * * *")
        assert job_id is not None
        assert 1 in [t["topic_id"] for t in scheduler.get_scheduled_topics()]

    @pytest.mark.asyncio
    async def test_add_topic_with_next_run(self, scheduler):
        """Scheduled topic should have a next_run time."""
        scheduler.add_topic(1, "0 6 * * *")
        next_run = scheduler.get_next_run(1)
        assert next_run is not None

    @pytest.mark.asyncio
    async def test_remove_topic(self, scheduler):
        """Should remove a topic's schedule."""
        scheduler.add_topic(1, "0 6 * * *")
        scheduler.remove_topic(1)
        assert scheduler.get_next_run(1) is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_topic(self, scheduler):
        """Removing a non-scheduled topic should not error."""
        scheduler.remove_topic(999)  # Should not raise

    @pytest.mark.asyncio
    async def test_replace_schedule(self, scheduler):
        """Adding a topic again should replace its schedule."""
        scheduler.add_topic(1, "0 6 * * *")
        scheduler.add_topic(1, "30 8 * * *")
        topics = scheduler.get_scheduled_topics()
        assert len([t for t in topics if t["topic_id"] == 1]) == 1

    @pytest.mark.asyncio
    async def test_invalid_cron_raises(self, scheduler):
        """Invalid cron expression should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid cron"):
            scheduler.add_topic(1, "not a cron")

    @pytest.mark.asyncio
    async def test_multiple_topics(self, scheduler):
        """Should manage multiple topic schedules."""
        scheduler.add_topic(1, "0 6 * * *")
        scheduler.add_topic(2, "0 12 * * *")
        scheduler.add_topic(3, "0 18 * * *")
        topics = scheduler.get_scheduled_topics()
        assert len(topics) == 3


class TestManualTrigger:
    @pytest.mark.asyncio
    async def test_trigger_now(self, scheduler, run_log):
        """Should execute the callback immediately."""
        await scheduler.trigger_now(42)
        assert 42 in run_log

    @pytest.mark.asyncio
    async def test_trigger_callback_error_handled(self):
        """Callback errors should be caught, not crash the scheduler."""
        async def failing_callback(topic_id):
            raise RuntimeError("Test error")

        mgr = SchedulerManager(run_callback=failing_callback)
        mgr.start()
        try:
            await mgr.trigger_now(1)  # Should not raise
        finally:
            mgr.shutdown()
