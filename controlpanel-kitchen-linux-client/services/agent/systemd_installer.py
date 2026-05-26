"""Systemd user-unit installer for the CPK agent service.

Generates ``~/.config/systemd/user/<name>.service`` files from ``REGISTRY``
and manages them via ``systemctl --user``.

Typical lifecycle::

    installer = SystemdInstaller()
    installer.install()    # write units + daemon-reload + enable + start
    installer.uninstall()  # stop + disable + remove units + daemon-reload
    installer.start()      # systemctl --user start <all>
    installer.stop()       # systemctl --user stop <all>
    installer.status()     # prints systemctl --user status <all>
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from services.agent.processes import REGISTRY, ProcessSpec

logger = logging.getLogger(__name__)

_UNIT_DIR = Path.home() / ".config" / "systemd" / "user"

_CLEANUP_SERVICE_NAME = "cpk-cleanup"
_CLEANUP_MODULE = "services.agent.workers.cleanup"
_CLEANUP_DESCRIPTION = "CPK agent cleanup — purge old completed tasks"
_CLEANUP_TIMER_SCHEDULE = "daily"  # OnCalendar value; change to e.g. 'hourly' if needed

_SERVICE_TEMPLATE = """\
[Unit]
Description={description}
After=network.target

[Service]
Type=simple
ExecStart={python} -m {module}
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
"""

_CLEANUP_SERVICE_TEMPLATE = """\
[Unit]
Description={description}

[Service]
Type=oneshot
ExecStart={python} -m {module}
"""

_TIMER_TEMPLATE = """\
[Unit]
Description={description} (timer)

[Timer]
OnCalendar={schedule}
Persistent=true

[Install]
WantedBy=timers.target
"""


def _unit_name(spec: ProcessSpec) -> str:
    return f"{spec.name}.service"


def _unit_path(spec: ProcessSpec) -> Path:
    return _UNIT_DIR / _unit_name(spec)


def _systemctl(*args: str) -> None:
    """Run ``systemctl --user <args>`` and log the call."""
    cmd = ["systemctl", "--user", *args]
    logger.debug("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _python_executable() -> str:
    """Return the absolute path to the current Python interpreter."""
    return sys.executable


class SystemdInstaller:
    """Manages systemd user units for every entry in ``REGISTRY``."""

    # ------------------------------------------------------------------
    # High-level operations
    # ------------------------------------------------------------------

    def install(self) -> None:
        """Write unit files, reload daemon, enable and start all services."""
        _UNIT_DIR.mkdir(parents=True, exist_ok=True)
        for spec in REGISTRY:
            self._write_unit(spec)
        self._write_cleanup_units()
        self._daemon_reload()
        for spec in REGISTRY:
            _systemctl("enable", _unit_name(spec))
            _systemctl("start", _unit_name(spec))
        _systemctl("enable", f"{_CLEANUP_SERVICE_NAME}.timer")
        _systemctl("start", f"{_CLEANUP_SERVICE_NAME}.timer")
        logger.info("All CPK agent units installed and started.")

    def uninstall(self) -> None:
        """Stop, disable and remove all unit files, then reload daemon."""
        for spec in REGISTRY:
            try:
                _systemctl("stop", _unit_name(spec))
            except subprocess.CalledProcessError:
                pass  # already stopped — fine
            try:
                _systemctl("disable", _unit_name(spec))
            except subprocess.CalledProcessError:
                pass
            path = _unit_path(spec)
            if path.exists():
                path.unlink()
                logger.info("Removed %s", path)
        for suffix in ("timer", "service"):
            unit = f"{_CLEANUP_SERVICE_NAME}.{suffix}"
            try:
                _systemctl("stop", unit)
            except subprocess.CalledProcessError:
                pass
            try:
                _systemctl("disable", unit)
            except subprocess.CalledProcessError:
                pass
            path = _UNIT_DIR / unit
            if path.exists():
                path.unlink()
                logger.info("Removed %s", path)
        self._daemon_reload()
        logger.info("All CPK agent units removed.")

    def start(self) -> None:
        """Start all registered services and the cleanup timer via systemctl."""
        for spec in REGISTRY:
            _systemctl("start", _unit_name(spec))
        _systemctl("start", f"{_CLEANUP_SERVICE_NAME}.timer")

    def stop(self) -> None:
        """Stop all registered services and the cleanup timer via systemctl."""
        for spec in REGISTRY:
            _systemctl("stop", _unit_name(spec))
        _systemctl("stop", f"{_CLEANUP_SERVICE_NAME}.timer")

    def status(self) -> None:
        """Print systemctl status for all registered services (non-raising)."""
        for spec in REGISTRY:
            subprocess.run(
                ["systemctl", "--user", "status", _unit_name(spec)],
                check=False,
            )
        for suffix in ("timer", "service"):
            subprocess.run(
                ["systemctl", "--user", "status", f"{_CLEANUP_SERVICE_NAME}.{suffix}"],
                check=False,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _write_unit(self, spec: ProcessSpec) -> None:
        content = _SERVICE_TEMPLATE.format(
            description=spec.description,
            python=_python_executable(),
            module=spec.module,
        )
        path = _unit_path(spec)
        path.write_text(content, encoding="utf-8")
        logger.info("Wrote %s", path)

    def _write_cleanup_units(self) -> None:
        """Write ``cpk-cleanup.service`` (oneshot) and ``cpk-cleanup.timer``."""
        python = _python_executable()

        service_content = _CLEANUP_SERVICE_TEMPLATE.format(
            description=_CLEANUP_DESCRIPTION,
            python=python,
            module=_CLEANUP_MODULE,
        )
        service_path = _UNIT_DIR / f"{_CLEANUP_SERVICE_NAME}.service"
        service_path.write_text(service_content, encoding="utf-8")
        logger.info("Wrote %s", service_path)

        timer_content = _TIMER_TEMPLATE.format(
            description=_CLEANUP_DESCRIPTION,
            schedule=_CLEANUP_TIMER_SCHEDULE,
        )
        timer_path = _UNIT_DIR / f"{_CLEANUP_SERVICE_NAME}.timer"
        timer_path.write_text(timer_content, encoding="utf-8")
        logger.info("Wrote %s", timer_path)

    @staticmethod
    def _daemon_reload() -> None:
        _systemctl("daemon-reload")
