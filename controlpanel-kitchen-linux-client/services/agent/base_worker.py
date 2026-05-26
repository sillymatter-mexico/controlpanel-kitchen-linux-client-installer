"""Base polling worker for the CPK agent service.

Subclass ``BaseWorker`` and implement ``handle(task)`` to create a worker
for a specific task type.  The base class handles:

- Claiming tasks atomically (``pending`` → ``running``) so multiple workers
  never double-process the same task.
- Calling ``handle()`` and committing ``done`` on success.
- Rolling back and marking ``failed`` on any unhandled exception.
- A configurable polling interval with a clean shutdown path.

Example::

    class PrintWorker(BaseWorker):
        task_type = "print"

        async def handle(self, task: Task) -> None:
            payload = json.loads(task.payload)
            await submit_to_cups(payload["content"])

    if __name__ == "__main__":
        asyncio.run(PrintWorker().run())
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod

from sqlalchemy import select, update

from models.database import get_db, init_db
from models.tasks import Task

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """Abstract base class for task-queue polling workers.

    Attributes:
        task_type: The value of ``Task.type`` this worker handles.
        poll_interval: Seconds to sleep between polls when no task is found.
    """

    task_type: str
    poll_interval: float = 2.0

    def __init__(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Initialise the DB and poll continuously until ``stop()`` is called."""
        await init_db()
        self._running = True
        logger.info("[%s] worker started (polling every %.1fs)", self.task_type, self.poll_interval)
        while self._running:
            claimed = await self._claim_next()
            if claimed is None:
                await asyncio.sleep(self.poll_interval)
                continue
            await self._process(claimed)

    def stop(self) -> None:
        """Request a clean shutdown after the current task finishes."""
        self._running = False

    # ------------------------------------------------------------------
    # Abstract hook
    # ------------------------------------------------------------------

    @abstractmethod
    async def handle(self, task: Task) -> None:
        """Execute the work for *task*.

        Raise any exception to mark the task as ``failed``.
        """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _claim_next(self) -> Task | None:
        """Atomically transition the oldest pending task to ``running``.

        Returns the claimed ``Task``, or ``None`` if the queue is empty.
        """
        async with get_db() as session:
            # SELECT … LIMIT 1 FOR UPDATE is not supported by SQLite;
            # we rely on the serialised writer lock instead.
            result = await session.execute(
                select(Task)
                .where(Task.type == self.task_type, Task.status == "pending")
                .order_by(Task.created_at)
                .limit(1)
                .with_for_update(skip_locked=False)
            )
            task = result.scalar_one_or_none()
            if task is None:
                return None

            await session.execute(
                update(Task)
                .where(Task.id == task.id, Task.status == "pending")
                .values(status="running")
            )
            await session.commit()
            # Refresh so the returned object reflects the new status
            await session.refresh(task)
            return task

    async def _process(self, task: Task) -> None:
        """Call ``handle()`` and update the task status accordingly."""
        logger.info("[%s] processing task id=%d", self.task_type, task.id)
        try:
            await self.handle(task)
            await self._set_status(task.id, "done")
            logger.info("[%s] task id=%d done", self.task_type, task.id)
        except Exception as exc:
            logger.exception("[%s] task id=%d failed: %s", self.task_type, task.id, exc)
            await self._set_status(task.id, "failed")

    @staticmethod
    async def _set_status(task_id: int, status: str) -> None:
        async with get_db() as session:
            await session.execute(
                update(Task).where(Task.id == task_id).values(status=status)
            )
            await session.commit()
