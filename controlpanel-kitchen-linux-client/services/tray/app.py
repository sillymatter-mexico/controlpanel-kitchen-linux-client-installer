"""System tray icon for the CPK agent service.

Displays the WebSocket connection status and provides a context menu to
start / stop / restart the background agent processes via ``systemctl --user``.

The icon colour reflects the current connection state read from
``~/.cpk/ws_status.json`` (written by the WS listener):

    green  -> connected
    yellow -> connecting / reconnecting
    red    -> disconnected / error / no_token
    grey   -> unknown / file missing

Requirements (add to your venv)::

    pip install pystray Pillow

Run as a module::

    python -m services.tray
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Any

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pystray and Pillow are required.\n"
        "Install them with:  pip install pystray Pillow"
    ) from exc

from services.agent.processes import REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (kept in sync with services/agent/listener.py)
# ---------------------------------------------------------------------------

_CPK_DIR = Path.home() / ".cpk"
_STATUS_FILE = _CPK_DIR / "ws_status.json"

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------

_POLL_INTERVAL: float = 3.0   # seconds between status-file reads
_ICON_SIZE: int = 64

_COLORS: dict[str, tuple[int, int, int]] = {
    "connected":    (34,  197, 94),   # green-500
    "connecting":   (234, 179, 8),    # yellow-500
    "reconnecting": (234, 179, 8),    # yellow-500
    "disconnected": (239, 68,  68),   # red-500
    "error":        (239, 68,  68),   # red-500
    "failed":       (239, 68,  68),   # red-500
    "no_token":     (239, 68,  68),   # red-500
}
_COLOR_UNKNOWN: tuple[int, int, int] = (156, 163, 175)  # gray-400

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_status() -> dict[str, Any]:
    """Return the contents of ws_status.json, or {} on any failure."""
    try:
        if _STATUS_FILE.exists():
            return json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _status_color(status: str) -> tuple[int, int, int]:
    return _COLORS.get(status.lower(), _COLOR_UNKNOWN)


def _make_icon(color: tuple[int, int, int]) -> Image.Image:
    """Draw a filled circle on a transparent background."""
    img = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    m = 6  # margin
    draw.ellipse([m, m, _ICON_SIZE - m, _ICON_SIZE - m], fill=(*color, 255))
    return img


def _service_names() -> list[str]:
    return [f"{spec.name}.service" for spec in REGISTRY]


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = ["systemctl", "--user", *args]
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True)


def _run_systemctl_action(action: str, names: list[str] | None = None) -> None:
    """Execute a systemctl action against the given services (default: all)."""
    names = names if names is not None else _service_names()
    logger.info("%s: %s", action, ", ".join(names))
    result = _systemctl(action, *names)
    if result.returncode != 0:
        logger.warning(
            "systemctl %s failed (rc=%d): %s",
            action, result.returncode, result.stderr.strip(),
        )
    else:
        logger.info("systemctl %s succeeded.", action)


# ---------------------------------------------------------------------------
# Tray application
# ---------------------------------------------------------------------------


class CPKTray:
    """Manages the system tray icon and context menu for the CPK agent."""

    def __init__(self) -> None:
        self._status: dict[str, Any] = {}
        self._icon: pystray.Icon | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _service_submenu(self, service_unit: str) -> pystray.Menu:
        """Return a submenu with Restart / Start / Stop for a single service."""
        def _action(act: str):
            def cb(icon: pystray.Icon, item: pystray.MenuItem) -> None:
                threading.Thread(
                    target=_run_systemctl_action,
                    args=(act, [service_unit]),
                    daemon=True,
                ).start()
            return cb

        return pystray.Menu(
            pystray.MenuItem("Restart", _action("restart")),
            pystray.MenuItem("Start",   _action("start")),
            pystray.MenuItem("Stop",    _action("stop")),
        )

    def _build_menu(self) -> pystray.Menu:
        ws_status = self._status.get("status", "unknown")
        attempts = self._status.get("reconnect_attempts", 0)
        updated = self._status.get("updated_at", "-")

        status_label = f"WS status: {ws_status}"
        if attempts:
            status_label += f"  (retries: {attempts})"

        service_items = [
            pystray.MenuItem(spec.name, self._service_submenu(f"{spec.name}.service"))
            for spec in REGISTRY
        ]

        return pystray.Menu(
            pystray.MenuItem(status_label, None, enabled=False),
            pystray.MenuItem(f"Last update: {updated}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Services", pystray.Menu(*service_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart all", self._on_restart),
            pystray.MenuItem("Start all",   self._on_start),
            pystray.MenuItem("Stop all",    self._on_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit tray", self._on_quit),
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_restart(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        threading.Thread(target=_run_systemctl_action, args=("restart",), daemon=True).start()

    def _on_start(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        threading.Thread(target=_run_systemctl_action, args=("start",), daemon=True).start()

    def _on_stop(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        threading.Thread(target=_run_systemctl_action, args=("stop",), daemon=True).start()

    def _on_quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        logger.info("CPK tray exiting.")
        self._stop_event.set()
        icon.stop()

    # ------------------------------------------------------------------
    # Background poller
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Periodically refresh the icon and menu from the status file."""
        while not self._stop_event.wait(_POLL_INTERVAL):
            new_status = _read_status()
            if new_status != self._status:
                self._status = new_status
                self._apply_status()

    def _apply_status(self) -> None:
        if self._icon is None:
            return
        ws_status = self._status.get("status", "unknown")
        color = _status_color(ws_status)
        self._icon.icon = _make_icon(color)
        self._icon.title = f"CPK Agent - {ws_status}"
        self._icon.menu = self._build_menu()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Create the icon and block until the user chooses *Quit tray*."""
        self._status = _read_status()
        ws_status = self._status.get("status", "unknown")

        self._icon = pystray.Icon(
            name="cpk-agent",
            icon=_make_icon(_status_color(ws_status)),
            title=f"CPK Agent - {ws_status}",
            menu=self._build_menu(),
        )

        poller = threading.Thread(
            target=self._poll_loop, daemon=True, name="cpk-tray-poller"
        )
        poller.start()

        logger.info("CPK tray icon started.")
        self._icon.run()
        logger.info("CPK tray icon stopped.")


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def run() -> None:
    """Start the tray application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    CPKTray().run()
