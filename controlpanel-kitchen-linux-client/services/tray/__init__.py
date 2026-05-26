"""services.tray — system tray icon for the CPK agent.

All implementation lives in :mod:`services.tray.app`.
This module re-exports the public API for convenience.
"""

from services.tray.app import CPKTray, run

__all__ = ["CPKTray", "run"]
