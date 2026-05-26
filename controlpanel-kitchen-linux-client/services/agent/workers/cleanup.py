"""One-shot cleanup job for the CPK agent service.

Deletes completed (``done`` / ``failed``) tasks that are older than
``RETENTION_DAYS`` from the local SQLite database.  Designed to be run
periodically by ``cpk-cleanup.timer`` (systemd) or a simple schedule in dev.

Usage::

    python -m services.agent.workers.cleanup
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from models.database import get_db, init_db
from models.tasks import Task

logger = logging.getLogger(__name__)

#: Tasks older than this many days with a terminal status are purged.
RETENTION_DAYS: int = 7


async def _run_cleanup() -> None:
    await init_db()

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=RETENTION_DAYS)
    terminal_statuses = ("done", "failed")

    async with get_db() as session:
        result = await session.execute(
            delete(Task).where(
                Task.status.in_(terminal_statuses),
                Task.updated_at < cutoff,
            )
        )
        deleted = result.rowcount
        await session.commit()

    logger.info(
        "Cleanup complete: removed %d task(s) older than %d day(s).",
        deleted,
        RETENTION_DAYS,
    )


def main() -> None:
    from services.agent.logging_config import configure
    configure()
    asyncio.run(_run_cleanup())


if __name__ == "__main__":
    main()
