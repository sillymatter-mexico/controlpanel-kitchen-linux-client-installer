"""Entry point for the ControlPanel Kitchen CLI."""

from __future__ import annotations

import typer

from cli.commands import agent, auth, deploy

app = typer.Typer(
    name="cpk",
    help="ControlPanel Kitchen command-line interface.",
    no_args_is_help=True,
)

app.add_typer(auth.app, name="auth")
app.add_typer(agent.app, name="agent")
app.add_typer(deploy.app, name="deploy")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
