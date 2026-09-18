"""Unit tests for background TaskScheduler and SQLite persistent job queue."""

import asyncio
import pytest
from core.scheduler import ScheduledJob, TaskScheduler


@pytest.mark.asyncio
async def test_scheduler_crud_and_persistence(tmp_path):
  """Test creating, listing, cancelling, and deleting scheduled jobs."""
  db_file = tmp_path / "scheduler_test.sqlite"
  scheduler = TaskScheduler(db_path=db_file)

  # 1. Add jobs
  job1 = scheduler.add_job(
      name="Workspace Sync",
      interval_seconds=60.0,
      action_type="sync",
      payload={"target": "git"},
  )
  job2 = scheduler.add_job(
      name="Heartbeat Telemetry",
      interval_seconds=300.0,
      action_type="heartbeat",
  )

  assert job1.job_id is not None

  # 2. List jobs
  jobs = scheduler.list_jobs()
  assert len(jobs) == 2

  # 3. Get single job
  fetched = scheduler.get_job(job1.job_id)
  assert fetched is not None
  assert fetched.name == "Workspace Sync"
  assert fetched.is_active is True

  # 4. Cancel job
  scheduler.cancel_job(job1.job_id)
  active_jobs = scheduler.list_jobs(only_active=True)
  assert len(active_jobs) == 1
  assert active_jobs[0].job_id == job2.job_id

  # 5. Delete job
  scheduler.delete_job(job2.job_id)
  all_remaining = scheduler.list_jobs()
  assert len(all_remaining) == 1


@pytest.mark.asyncio
async def test_scheduler_tick_execution(tmp_path):
  """Test that scheduler _tick executes handler and increments run_count."""
  db_file = tmp_path / "scheduler_tick.sqlite"
  executed_jobs = []

  async def mock_handler(job: ScheduledJob):
    executed_jobs.append(job.name)

  scheduler = TaskScheduler(db_path=db_file, execution_handler=mock_handler)
  job = scheduler.add_job(
      name="Test Immediate Job",
      interval_seconds=10.0,
      start_immediately=True,
  )

  await scheduler._tick()

  assert len(executed_jobs) == 1
  assert executed_jobs[0] == "Test Immediate Job"

  updated = scheduler.get_job(job.job_id)
  assert updated.run_count == 1
  assert updated.last_run is not None
