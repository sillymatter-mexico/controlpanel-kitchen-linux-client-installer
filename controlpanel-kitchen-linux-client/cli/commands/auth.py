"""Authentication commands (login, logout, whoami)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from cpk_sdk.client.exceptions import APIError
from cpk_sdk.client.http_client import ControlPanelKitchenClient
from cpk_sdk.client.models.generated import UserTokenLoginRequestRequest

CPK_ORGANIZATION_SHORT_NAME = "CP-K"


class InvalidOrganizationError(Exception):
    """Raised when the token does not belong to the CP-K organization."""

    def __init__(self, short_name: str | None) -> None:
        super().__init__(
            f"Token belongs to organization '{short_name}', not '{CPK_ORGANIZATION_SHORT_NAME}'. "
            "Admin login is only allowed for CP-K."
        )


class PublicAdminTokenError(Exception):
    """Raised when the supplied admin token is marked as public."""

    def __init__(self) -> None:
        super().__init__("The provided token is a public token and cannot be used as an admin token.")


app = typer.Typer(help="Manage authentication.")

# ~/.cpk/credentials.json stores {"token": "Token abc123"}
_CREDENTIALS_FILE = Path.home() / ".cpk" / "credentials.json"


def _save_credentials(token: str, device_name: str) -> None:
    _CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Preserve admin_token if one was already stored.
    existing: dict = {}
    if _CREDENTIALS_FILE.exists():
        existing = json.loads(_CREDENTIALS_FILE.read_text())
    existing.update({"token": token, "device_name": device_name})
    _CREDENTIALS_FILE.write_text(json.dumps(existing))
    _CREDENTIALS_FILE.chmod(0o600)


def _load_token() -> str | None:
    if _CREDENTIALS_FILE.exists():
        data = json.loads(_CREDENTIALS_FILE.read_text())
        return data.get("token")
    return None


def _load_admin_token() -> str | None:
    if _CREDENTIALS_FILE.exists():
        data = json.loads(_CREDENTIALS_FILE.read_text())
        return data.get("admin_token")
    return None


async def _do_login(username: str, password: str) -> str:
    async with ControlPanelKitchenClient() as client:
        response = await client.auth.login_create(
            UserTokenLoginRequestRequest(username=username, password=password)
        )
    return response.token


@app.command()
def login(
    username: str = typer.Option(
        ...,
        prompt="Username",
        help="Your ControlPanel Kitchen username.",
    ),
    password: str = typer.Option(
        ...,
        prompt="Password",
        hide_input=True,
        help="Your ControlPanel Kitchen password.",
    ),
    device_name: str = typer.Option(
        ...,
        prompt="Device name",
        help="A name to identify this device.",
    ),
) -> None:
    """Log in and save your API token locally."""
    try:
        token = asyncio.run(_do_login(username, password))
    except APIError as exc:
        typer.secho(f"Login failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    _save_credentials(token, device_name)
    typer.echo(f"Logged in successfully. Token saved to {_CREDENTIALS_FILE}")


@app.command()
def logout() -> None:
    """Remove the stored API token."""
    if _CREDENTIALS_FILE.exists():
        _CREDENTIALS_FILE.unlink()
        typer.echo("Logged out. Credentials removed.")
    else:
        typer.echo("No stored credentials found.")


@app.command()
def whoami() -> None:
    """Show the currently authenticated user."""
    token = _load_token()
    if not token:
        typer.secho("Not logged in. Run `cpk auth login` first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    async def _me() -> None:
        async with ControlPanelKitchenClient(token=token) as client:
            me = await client.auth.me_retrieve()
        typer.echo(f"Logged in as: {me.user.username}")
        typer.echo(f"Organization: {me.organization.name}")

    try:
        asyncio.run(_me())
    except APIError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


async def _verify_admin_token(admin_token: str) -> None:
    """Verify the token belongs to CP-K and is not a public token."""
    # Strip the optional "Token " prefix to get the raw key for comparison.
    raw_key = admin_token.removeprefix("Token ").strip()

    async with ControlPanelKitchenClient(token=admin_token) as client:
        me = await client.auth.me_retrieve()

        if me.organization is None:
            raise InvalidOrganizationError(None)

        short_name = me.organization.short_name
        if short_name != CPK_ORGANIZATION_SHORT_NAME:
            raise InvalidOrganizationError(short_name)

        # Paginate through the org's tokens to find this one and check is_public.
        org_uuid = me.organization.uuid
        if org_uuid:
            offset = 0
            limit = 100
            while True:
                page = await client.organizations.tokens_list(
                    org_uuid, limit=limit, offset=offset
                )
                for token_obj in (page.results or []):
                    if token_obj.key == raw_key:
                        if token_obj.is_public:
                            raise PublicAdminTokenError()
                        return  # found and valid
                if page.next is None:
                    break
                offset += limit


@app.command("admin-login")
def admin_login(
    admin_token: str = typer.Option(
        ...,
        prompt="Admin token",
        hide_input=True,
        help="API token for the CP-K admin organization.",
    ),
) -> None:
    """Store a CP-K admin token after verifying organization membership."""
    try:
        asyncio.run(_verify_admin_token(admin_token))
    except PublicAdminTokenError as exc:
        typer.secho(f"Admin login failed [{type(exc).__name__}]: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except InvalidOrganizationError as exc:
        typer.secho(f"Admin login failed [{type(exc).__name__}]: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except APIError as exc:
        status = f" (HTTP {exc.status_code})" if exc.status_code is not None else ""
        path = f" [{exc.response.request.url.path}]" if exc.response is not None else ""
        typer.secho(f"Admin login failed [{type(exc).__name__}]{status}{path}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Merge into existing credentials (preserves token/device_name if present).
    existing: dict = {}
    if _CREDENTIALS_FILE.exists():
        existing = json.loads(_CREDENTIALS_FILE.read_text())
    existing["admin_token"] = admin_token
    _CREDENTIALS_FILE.write_text(json.dumps(existing))
    _CREDENTIALS_FILE.chmod(0o600)
    typer.echo(f"Admin token saved to {_CREDENTIALS_FILE}")
