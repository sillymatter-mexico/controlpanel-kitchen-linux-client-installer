"""Deploy command — bump version, build sdist, upload, commit, and push."""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
from pathlib import Path

import typer

from cli.commands.auth import _load_admin_token
from cpk_sdk.client.exceptions import APIError, raise_for_status
from cpk_sdk.client.http_client import ControlPanelKitchenClient

app = typer.Typer(help="Build and publish a new client release.")

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT / "VERSION"
DIST_DIR = ROOT / "dist"
CLIENT_NAME = "controlpanel-kitchen-linux-client"
CLIENT_TYPE = "python-linux-client"
CLIENT_SOURCE = "deploy-script"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(args: list[str], *, check: bool = False, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=check,
        capture_output=capture,
        text=capture,
    )


def _check_git_clean() -> None:
    """Abort if the working tree has uncommitted changes or unpushed commits."""
    status = _run(["git", "status", "--porcelain"], capture=True)
    if status.returncode != 0:
        typer.secho(f"git error: {status.stderr.strip()}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if status.stdout.strip():
        typer.secho(
            "Working tree is not clean — commit or stash all changes before deploying.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    _run(["git", "fetch"], capture=True)

    ahead = _run(["git", "rev-list", "--count", "@{u}..HEAD"], capture=True)
    if ahead.returncode == 0 and ahead.stdout.strip() not in ("0", ""):
        typer.secho(
            "Branch has unpushed commits — push first before deploying.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)


def _bump_version(part: str) -> tuple[str, str]:
    """Bump the version in pyproject.toml and sync VERSION file.

    Returns (old_version, new_version).
    """
    old = VERSION_FILE.read_text().strip()
    _run(["poetry", "version", part], check=True)
    result = _run(["poetry", "version", "--short"], capture=True)
    new = result.stdout.strip()
    VERSION_FILE.write_text(new + "\n")
    return old, new


def _rollback_version(old: str) -> None:
    _run(["git", "checkout", "--", "pyproject.toml"], capture=True)
    VERSION_FILE.write_text(old + "\n")


def _collect_release_notes() -> str:
    """Return one-line commit subjects since the last [deploy] commit."""
    # Find the hash of the most recent [deploy] commit.
    last = _run(
        ["git", "log", "--grep=[deploy]", "-1", "--pretty=format:%H"],
        capture=True,
    )
    since_ref = last.stdout.strip()

    if since_ref:
        log = _run(
            ["git", "log", f"{since_ref}..HEAD", "--pretty=format:- %s"],
            capture=True,
        )
    else:
        # No previous deploy — include all commits.
        log = _run(
            ["git", "log", "--pretty=format:- %s"],
            capture=True,
        )

    return log.stdout.strip()


async def _upload_build(token: str, version: str, tarball: Path, checksum: str, release_notes: str) -> None:
    """Upload the build artifact via multipart form data."""
    async with ControlPanelKitchenClient(token=token) as client:
        build_bytes = tarball.read_bytes()
        data: dict[str, str] = {
            "key": checksum,
            "version": version,
            "source": CLIENT_SOURCE,
            "client_name": CLIENT_NAME,
            "client_type": CLIENT_TYPE,
            "checksum": checksum,
        }
        if release_notes:
            data["release_notes"] = release_notes
        response = await client._http.post(
            "/api/server/client-deploys/",
            data=data,
            files={"build": (tarball.name, build_bytes, "application/gzip")},
        )
        raise_for_status(response)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@app.command()
def create(
    bump: str = typer.Option(
        "patch",
        help="Version segment to bump before building: major, minor, or patch.",
    ),
) -> None:
    """Check git, bump version, build sdist, upload to API, then commit and push."""
    if bump not in ("major", "minor", "patch"):
        typer.secho("--bump must be one of: major, minor, patch.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    token = _load_admin_token()
    if not token:
        typer.secho(
            "No admin token found. Run `cpk auth admin-login` first.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    # 1. Check git is clean and nothing to push.
    typer.echo("Checking git status…")
    _check_git_clean()
    typer.secho("  ✓ Git is clean.", fg=typer.colors.GREEN)

    # 2. Bump version.
    old_version, new_version = _bump_version(bump)
    typer.echo(f"Version: {old_version} → {new_version}")

    # 3. Build source distribution (produces dist/*.tar.gz).
    typer.echo("Building sdist…")
    build_result = _run(["poetry", "build", "--format", "sdist"])
    if build_result.returncode != 0:
        _rollback_version(old_version)
        typer.secho("Build failed — version rolled back.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    candidates = sorted(DIST_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        _rollback_version(old_version)
        typer.secho("No .tar.gz found in dist/ — version rolled back.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    tarball = candidates[-1]
    typer.secho(f"  ✓ Artifact: {tarball.name}", fg=typer.colors.GREEN)

    # 4. Compute SHA-256 checksum.
    checksum = hashlib.sha256(tarball.read_bytes()).hexdigest()
    typer.echo(f"  SHA-256 : {checksum}")

    # 5. Collect release notes from git history since last [deploy].
    release_notes = _collect_release_notes()
    if release_notes:
        typer.echo(f"Release notes:\n{release_notes}")

    # 6. Upload to API.
    typer.echo("Uploading to API…")
    try:
        asyncio.run(_upload_build(token, new_version, tarball, checksum, release_notes))
    except APIError as exc:
        _rollback_version(old_version)
        typer.secho(
            f"Upload failed: {exc}\nVersion rolled back to {old_version}.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    typer.secho("  ✓ Upload successful.", fg=typer.colors.GREEN)

    # 7. Commit VERSION + pyproject.toml and push.
    commit_msg = f"[deploy] {new_version}:{checksum}"
    typer.echo(f"Committing: {commit_msg}")
    _run(["git", "add", str(VERSION_FILE), str(ROOT / "pyproject.toml")], check=True)
    _run(["git", "commit", "-m", commit_msg], check=True)
    _run(["git", "push"], check=True)

    typer.secho(f"\nDeployed {new_version} successfully!", fg=typer.colors.GREEN)
