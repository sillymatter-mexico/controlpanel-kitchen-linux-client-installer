"""Print worker — CUPS / lp integration."""

from __future__ import annotations

import asyncio
import json
import logging

from models.tasks import Task
from services.agent.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class PrintWorker(BaseWorker):
    """Polls for ``type="print"`` tasks and submits them to CUPS via ``lp``.

    Expected payload fields:
        content (str): Text to print. Falls back to the raw JSON payload.
        printer (str, optional): CUPS destination name. Omit for the default printer.
    """

    task_type = "print"

    async def handle(self, task: Task) -> None:
        payload = json.loads(task.payload)
        content: str = payload.get("content") or json.dumps(payload)
        printer: str | None = payload.get("printer")

        cmd = ["lp"]
        if printer:
            cmd += ["-d", printer]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(input=content.encode())
        if proc.returncode != 0:
            raise RuntimeError(
                f"lp exited {proc.returncode}: {stderr.decode().strip()}"
            )
        logger.info("Print job submitted via lp (task id=%d)", task.id)


def main() -> None:
    from services.agent.logging_config import configure
    configure()
    asyncio.run(PrintWorker().run())


if __name__ == "__main__":
    main()
