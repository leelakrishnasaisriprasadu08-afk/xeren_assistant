"""Persistent background task scheduler and recurring cron/interval engine."""

import asyncio
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class ScheduledJob(BaseModel):
  """Representation of a background scheduled job."""

  job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
  name: str
  interval_seconds: float
  action_type: str = "custom"  # "custom", "query", "tool"
  payload: Dict[str, Any] = Field(default_factory=dict)
  last_run: Optional[float] = None
  next_run: float = Field(default_factory=time.time)
  is_active: bool = True
  run_count: int = 0
  last_error: Optional[str] = None


class TaskScheduler:
  """Asynchronous persistent task scheduler running in background."""

  def __init__(
      self,
      db_path: Optional[Path] = None,
      execution_handler: Optional[Callable[[ScheduledJob], Any]] = None,
  ):
    self.db_path = (db_path or Path("data/xeren.sqlite")).resolve()
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self.execution_handler = execution_handler
    self._is_running = False
    self._loop_task: Optional[asyncio.Task] = None
    self._init_db()

  def _get_connection(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self.db_path))
    conn.row_factory = sqlite3.Row
    return conn

  def _init_db(self) -> None:
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute("""
              CREATE TABLE IF NOT EXISTS scheduled_jobs (
                  job_id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  interval_seconds REAL NOT NULL,
                  action_type TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  last_run REAL,
                  next_run REAL NOT NULL,
                  is_active INTEGER NOT NULL,
                  run_count INTEGER NOT NULL,
                  last_error TEXT
              )
              """)

  def add_job(
      self,
      name: str,
      interval_seconds: float,
      action_type: str = "custom",
      payload: Optional[Dict[str, Any]] = None,
      start_immediately: bool = True,
  ) -> ScheduledJob:
    """Registers and schedules a new background recurring job."""
    now = time.time()
    job = ScheduledJob(
        name=name,
        interval_seconds=interval_seconds,
        action_type=action_type,
        payload=payload or {},
        next_run=now if start_immediately else now + interval_seconds,
    )

    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute(
            """
                  INSERT OR REPLACE INTO scheduled_jobs 
                  (job_id, name, interval_seconds, action_type, payload_json, last_run, next_run, is_active, run_count, last_error)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  """,
            (
                job.job_id,
                job.name,
                job.interval_seconds,
                job.action_type,
                json.dumps(job.payload),
                job.last_run,
                job.next_run,
                1 if job.is_active else 0,
                job.run_count,
                job.last_error,
            ),
        )

    return job

  def get_job(self, job_id: str) -> Optional[ScheduledJob]:
    with closing(self._get_connection()) as conn:
      cursor = conn.execute(
          "SELECT * FROM scheduled_jobs WHERE job_id = ?", (job_id,)
      )
      row = cursor.fetchone()
      if not row:
        return None
      return ScheduledJob(
          job_id=row["job_id"],
          name=row["name"],
          interval_seconds=row["interval_seconds"],
          action_type=row["action_type"],
          payload=json.loads(row["payload_json"]),
          last_run=row["last_run"],
          next_run=row["next_run"],
          is_active=bool(row["is_active"]),
          run_count=row["run_count"],
          last_error=row["last_error"],
      )

  def list_jobs(self, only_active: bool = False) -> List[ScheduledJob]:
    with closing(self._get_connection()) as conn:
      query = (
          "SELECT * FROM scheduled_jobs WHERE is_active = 1"
          if only_active
          else "SELECT * FROM scheduled_jobs"
      )
      cursor = conn.execute(query)
      rows = cursor.fetchall()
      return [
          ScheduledJob(
              job_id=r["job_id"],
              name=r["name"],
              interval_seconds=r["interval_seconds"],
              action_type=r["action_type"],
              payload=json.loads(r["payload_json"]),
              last_run=r["last_run"],
              next_run=r["next_run"],
              is_active=bool(r["is_active"]),
              run_count=r["run_count"],
              last_error=r["last_error"],
          )
          for r in rows
      ]

  def cancel_job(self, job_id: str) -> bool:
    with closing(self._get_connection()) as conn:
      with conn:
        cursor = conn.execute(
            "UPDATE scheduled_jobs SET is_active = 0 WHERE job_id = ?",
            (job_id,),
        )
        return cursor.rowcount > 0

  def delete_job(self, job_id: str) -> bool:
    with closing(self._get_connection()) as conn:
      with conn:
        cursor = conn.execute(
            "DELETE FROM scheduled_jobs WHERE job_id = ?", (job_id,)
        )
        return cursor.rowcount > 0

  async def _tick(self) -> None:
    """Checks and executes pending scheduled jobs."""
    now = time.time()
    active_jobs = self.list_jobs(only_active=True)

    for job in active_jobs:
      if now >= job.next_run:
        job.last_run = now
        job.next_run = now + job.interval_seconds
        job.run_count += 1
        job.last_error = None

        if self.execution_handler:
          try:
            if asyncio.iscoroutinefunction(self.execution_handler):
              await self.execution_handler(job)
            else:
              self.execution_handler(job)
          except Exception as e:
            job.last_error = str(e)

        # Update in database
        with closing(self._get_connection()) as conn:
          with conn:
            conn.execute(
                """
                          UPDATE scheduled_jobs 
                          SET last_run = ?, next_run = ?, run_count = ?, last_error = ?
                          WHERE job_id = ?
                          """,
                (
                    job.last_run,
                    job.next_run,
                    job.run_count,
                    job.last_error,
                    job.job_id,
                ),
            )

  async def start(self, poll_interval: float = 1.0) -> None:
    """Starts the background scheduler loop."""
    if self._is_running:
      return
    self._is_running = True

    async def _runner():
      while self._is_running:
        try:
          await self._tick()
        except Exception:
          pass
        await asyncio.sleep(poll_interval)

    self._loop_task = asyncio.create_task(_runner())

  def stop(self) -> None:
    """Stops the scheduler loop."""
    self._is_running = False
    if self._loop_task:
      self._loop_task.cancel()
      self._loop_task = None
