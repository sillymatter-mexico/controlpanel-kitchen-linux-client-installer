"""WS Listener — connects to the CPK server and enqueues tasks.

Connects via ``CommanderConnection``, maps incoming events to task types,
and inserts rows into the local ``tasks`` table.  Reconnects on disconnect
with exponential backoff.

Connection state is written to ``~/.cpk/ws_status.json`` so other processes
(e.g. ``cpk agent status``) can read it without any IPC.

Run as a module::

    python -m services.agent.listener
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import insert

from cpk_sdk.client.ws_client import CPKWebSocketClient
from models.database import get_db, init_db
from models.tasks import Task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_CPK_DIR = Path.home() / ".cpk"
_CREDENTIALS_FILE = _CPK_DIR / "credentials.json"
_STATUS_FILE = _CPK_DIR / "ws_status.json"

# ---------------------------------------------------------------------------
# Event → task-type mapping
#
# Keys are the ``type`` or ``event`` field values received over the WS.
# Values are the ``Task.type`` strings the workers understand.
# Add new entries here as the server API grows.
# ---------------------------------------------------------------------------

EVENT_TASK_MAP: dict[str, str] = {
    "print_ticket": "print",
    "tts_message": "tts",
}

# ---------------------------------------------------------------------------
# Backoff config
# ---------------------------------------------------------------------------

_INITIAL_DELAY: float = 1.0
_MAX_DELAY: float = 60.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_token() -> str | None:
    if _CREDENTIALS_FILE.exists():
        data = json.loads(_CREDENTIALS_FILE.read_text(encoding="utf-8"))
        return data.get("token")
    return None


def _write_status(status: str, reconnect_attempts: int = 0) -> None:
    _CPK_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "reconnect_attempts": reconnect_attempts,
    }
    _STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.debug("WS status → %s", status)


async def _enqueue(event: dict) -> None:
    """Insert a task row for *event* if it maps to a known task type."""
    event_type = event.get("type") or event.get("event") or ""
    task_type = EVENT_TASK_MAP.get(event_type)
    if task_type is None:
        logger.debug("Ignoring unmapped event type %r", event_type)
        return

    payload = json.dumps(event)
    async with get_db() as session:
        await session.execute(
            insert(Task).values(type=task_type, payload=payload, status="pending")
        )
        await session.commit()
    logger.info("Enqueued task type=%r from event %r", task_type, event_type)


# ---------------------------------------------------------------------------
# Listener
# ---------------------------------------------------------------------------


class WSListener:
    """Connects to the CPK WS server and enqueues tasks for incoming events."""

    def __init__(self) -> None:
        self._running = False

    async def run(self) -> None:
        await init_db()
        self._running = True
        attempt = 0
        delay = _INITIAL_DELAY

        while self._running:
            token = _load_token()
            if not token:
                if attempt == 0:
                    logger.error(
                        "No auth token found at %s — run 'cpk auth login' first.",
                        _CREDENTIALS_FILE,
                    )
                _write_status("no_token", reconnect_attempts=attempt)
                await asyncio.sleep(delay)
                attempt += 1
                delay = min(delay * 2, _MAX_DELAY)
                continue

            _write_status("connecting", reconnect_attempts=attempt)
            if attempt == 0:
                logger.info("Connecting to CPK server…")
            else:
                logger.info("Reconnecting to CPK server (attempt %d)…", attempt)
            try:
                client = CPKWebSocketClient(token=token)
                async with client.commander(
                    client_name="cpk-linux-client",
                    device_name=socket.gethostname(),
                ) as conn:
                    _write_status("connected", reconnect_attempts=0)
                    attempt = 0
                    delay = _INITIAL_DELAY
                    logger.info("Connected to %s ✓", client._base_url)
                    async for event in conn.listen():
                        event_type = event.get("type") or event.get("event") or "unknown"
                        logger.info("← event: %s", event_type)
                        await _enqueue(event)

            except Exception as exc:
                if not self._running:
                    break
                logger.warning(
                    "Disconnected (%s) — retrying in %.0fs…",
                    exc,
                    delay,
                )
                _write_status("reconnecting", reconnect_attempts=attempt)
                await asyncio.sleep(delay)
                attempt += 1
                delay = min(delay * 2, _MAX_DELAY)

        _write_status("stopped")
        logger.info("WS listener stopped.")

    def stop(self) -> None:
        self._running = False


def main() -> None:
    from services.agent.logging_config import configure
    configure()
    asyncio.run(WSListener().run())


if __name__ == "__main__":
    main()
