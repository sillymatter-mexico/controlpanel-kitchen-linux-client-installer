"""Dev supervisor for the CPK agent service.

Spawns every process in ``REGISTRY`` as a subprocess (``python -m <module>``),
watches for crashes, and restarts them with exponential backoff.
A single ``Ctrl+C`` (SIGINT) or SIGTERM shuts everything down cleanly.

Usage::

    poetry run python -m services.agent.dev_supervisor
    # or via the CLI once wired up:
    cpk agent start
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path

from services.agent.processes import REGISTRY, ProcessSpec

logger = logging.getLogger(__name__)

_MAX_BACKOFF: float = 60.0  # seconds
_WATCH_INTERVAL: float = 1.0  # seconds between file-change polls


def _project_root() -> Path:
    """Walk up from this file to the directory that contains ``pyproject.toml``."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: three levels up from services/agent/dev_supervisor.py
    return Path(__file__).resolve().parents[2]


@dataclass
class _ManagedProcess:
    spec: ProcessSpec
    process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    restarts: int = 0
    _stopping: bool = field(default=False, repr=False)

    @property
    def backoff(self) -> float:
        """Exponential backoff capped at ``_MAX_BACKOFF``."""
        return min(self.spec.restart_delay * (2**self.restarts), _MAX_BACKOFF)


class DevSupervisor:
    """Runs all registry processes and restarts them on crash."""

    def __init__(self) -> None:
        self._managed: list[_ManagedProcess] = [
            _ManagedProcess(spec=spec) for spec in REGISTRY
        ]
        self._tasks: list[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        self._watcher_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start all processes and block until a shutdown signal is received."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._request_stop)

        root = _project_root()
        logger.info("Dev supervisor starting %d process(es)…", len(self._managed))
        logger.info("Watching *.py files under %s for changes (hot-reload)", root)

        self._tasks = [
            asyncio.create_task(self._supervise(mp), name=mp.spec.name)
            for mp in self._managed
        ]
        self._watcher_task = asyncio.create_task(
            self._file_watcher(root), name="file-watcher"
        )

        await self._stop_event.wait()
        await self._shutdown()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request_stop(self) -> None:
        logger.info("Shutdown requested — stopping all processes…")
        for mp in self._managed:
            mp._stopping = True
        self._stop_event.set()

    # ------------------------------------------------------------------
    # File-watcher (hot-reload)
    # ------------------------------------------------------------------

    async def _file_watcher(self, root: Path) -> None:
        """Poll ``*.py`` mtimes under *root*; reload children on any change."""

        def _snapshot() -> dict[str, float]:
            return {
                str(p): p.stat().st_mtime
                for p in root.rglob("*.py")
                if ".git" not in p.parts and "__pycache__" not in p.parts
            }

        previous = _snapshot()
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(asyncio.shield(self._stop_event.wait()), timeout=_WATCH_INTERVAL)
            except asyncio.TimeoutError:
                pass
            else:
                break  # stop event fired

            current = _snapshot()
            if current != previous:
                self._reload_children()
                previous = current

    def _reload_children(self) -> None:
        """SIGTERM all live children; the supervise loops will restart them."""
        logger.info("File change detected — reloading all worker processes…")
        for mp in self._managed:
            mp.restarts = 0  # reset backoff so the next start uses the initial delay
            proc = mp.process
            if proc is not None and proc.returncode is None:
                try:
                    proc.terminate()
                    logger.debug("[%s] SIGTERM sent for hot-reload (pid=%d)", mp.spec.name, proc.pid)
                except ProcessLookupError:
                    pass

    async def _start_process(self, mp: _ManagedProcess) -> None:
        """Launch ``python -m <module>`` for *mp* and store the handle."""
        mp.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            mp.spec.module,
            stdin=asyncio.subprocess.DEVNULL,
        )
        logger.info("[%s] started (pid=%d)", mp.spec.name, mp.process.pid)

    async def _supervise(self, mp: _ManagedProcess) -> None:
        """Keep *mp* alive until ``_stopping`` is set."""
        while not mp._stopping:
            try:
                await self._start_process(mp)
            except Exception as exc:
                logger.error("[%s] failed to start: %s", mp.spec.name, exc)
            else:
                await mp.process.wait()
                rc = mp.process.returncode

                if mp._stopping:
                    logger.info("[%s] exited (rc=%s) — supervisor stopping", mp.spec.name, rc)
                    return

                logger.warning(
                    "[%s] exited unexpectedly (rc=%s), restart #%d in %.1fs…",
                    mp.spec.name,
                    rc,
                    mp.restarts + 1,
                    mp.backoff,
                )

            delay = mp.backoff
            mp.restarts += 1
            try:
                await asyncio.wait_for(
                    asyncio.shield(asyncio.sleep(delay)),
                    timeout=delay + 1,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

    async def _shutdown(self) -> None:
        """Send SIGTERM to all live children and wait for them to exit."""
        if self._watcher_task is not None:
            self._watcher_task.cancel()
            await asyncio.gather(self._watcher_task, return_exceptions=True)

        for mp in self._managed:
            proc = mp.process
            if proc is not None and proc.returncode is None:
                try:
                    proc.terminate()
                    logger.debug("[%s] sent SIGTERM (pid=%d)", mp.spec.name, proc.pid)
                except ProcessLookupError:
                    pass

        # Cancel supervisor tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Give children a moment to exit gracefully, then SIGKILL stragglers
        await asyncio.sleep(0.5)
        for mp in self._managed:
            proc = mp.process
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                    logger.warning("[%s] killed (did not exit after SIGTERM)", mp.spec.name)
                except ProcessLookupError:
                    pass

        logger.info("Dev supervisor stopped.")


def main() -> None:
    from services.agent.logging_config import configure
    configure()
    asyncio.run(DevSupervisor().run())


if __name__ == "__main__":
    main()
