"""Agent service commands (start, install, uninstall, status)."""

from __future__ import annotations

import asyncio

import typer

app = typer.Typer(help="Manage the CPK agent background service.")


@app.command()
def start() -> None:
    """Start all agent processes in dev mode (restarts on crash, Ctrl+C to stop)."""
    from services.agent.dev_supervisor import DevSupervisor
    from services.agent.logging_config import configure

    configure()
    asyncio.run(DevSupervisor().run())


@app.command()
def install() -> None:
    """Generate systemd user units and start all agent services (prod)."""
    from services.agent.systemd_installer import SystemdInstaller

    SystemdInstaller().install()
    typer.echo("Agent services installed and started.")


@app.command()
def uninstall() -> None:
    """Stop, disable and remove systemd user units for all agent services."""
    from services.agent.systemd_installer import SystemdInstaller

    SystemdInstaller().uninstall()
    typer.echo("Agent services uninstalled.")


@app.command()
def status() -> None:
    """Show the running state of all agent services via systemctl."""
    from services.agent.systemd_installer import SystemdInstaller

    SystemdInstaller().status()
