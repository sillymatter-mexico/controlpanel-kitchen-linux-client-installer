"""Runtime configuration via environment variables or explicit kwargs."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Client settings — all values can be overridden with env vars."""

    model_config = SettingsConfigDict(env_prefix="CPK_", env_file=".env", extra="ignore")

    base_url: str = "https://api.controlpanel.kitchen"
    token: str | None = None
    timeout: float = 30.0
    # Optional: slug / host header expected by multi-tenant endpoints
    organization_host: str | None = None
