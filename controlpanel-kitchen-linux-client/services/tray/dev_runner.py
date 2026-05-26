"""Dev runner for the tray service.

Spawns ``services.tray`` as a subprocess, watches for ``*.py`` file
changes under the project root, and restarts the tray process on any
change — matching the hot-reload behaviour of the agent dev supervisor.

Run directly::

    python -m services.tray.dev_runner
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_WATCH_INTERVAL: float = 1.0  # seconds between mtime polls


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(__file__).resolve().parents[2]


def _snapshot(root: Path) -> dict[str, float]:
    return {
        str(p): p.stat().st_mtime
        for p in root.rglob("*.py")
        if ".git" not in p.parts and "__pycache__" not in p.parts
    }


def _start_tray() -> subprocess.Popen[bytes]:
    logger.info("[tray-dev] Starting tray process…")
    return subprocess.Popen(
        [sys.executable, "-m", "services.tray"],
        stdin=subprocess.DEVNULL,
    )


def _stop_tray(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    root = _project_root()
    logger.info("[tray-dev] Watching *.py under %s for changes (hot-reload)", root)

    proc_holder: list[subprocess.Popen[bytes] | None] = [_start_tray()]
    previous = _snapshot(root)

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("[tray-dev] Signal %d received — shutting down.", signum)
        if proc_holder[0] is not None:
            _stop_tray(proc_holder[0])
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while True:
        time.sleep(_WATCH_INTERVAL)

        proc = proc_holder[0]
        if proc is not None and proc.poll() is not None:
            logger.info("[tray-dev] Tray process exited (rc=%d) — restarting…", proc.returncode)
            proc_holder[0] = _start_tray()
            previous = _snapshot(root)
            continue

        current = _snapshot(root)
        if current != previous:
            logger.info("[tray-dev] File change detected — reloading tray…")
            if proc is not None:
                _stop_tray(proc)
            proc_holder[0] = _start_tray()
            previous = current


if __name__ == "__main__":
    run()
