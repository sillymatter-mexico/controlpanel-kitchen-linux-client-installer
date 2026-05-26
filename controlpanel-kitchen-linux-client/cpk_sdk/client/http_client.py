"""Core async HTTP client for the ControlPanel Kitchen API.

Usage
-----
    async with ControlPanelKitchenClient(token="Token abc123") as client:
        me = await client.auth.me()

Or driven by environment variables (prefix ``CPK_``):

    from cpk_sdk.client.settings import Settings
    async with ControlPanelKitchenClient.from_settings() as client:
        ...

Endpoint namespaces are lazy-loaded on first access, e.g.:

    client.auth          → cpk_sdk.client.endpoints.auth.AuthEndpoints
    client.collectors    → cpk_sdk.client.endpoints.collectors.CollectorsEndpoints
    client.restaurants   → cpk_sdk.client.endpoints.restaurants.RestaurantsEndpoints
    ...

Run ``make generate-endpoints`` to regenerate all endpoint modules from the
live OpenAPI schema.
"""

from __future__ import annotations

from typing import Any

import httpx

from cpk_sdk.client.endpoints._client_mixin import _GeneratedEndpointsMixin
from cpk_sdk.client.exceptions import raise_for_status
from cpk_sdk.client.settings import Settings


class ControlPanelKitchenClient(_GeneratedEndpointsMixin):
    """Async client that wraps the ControlPanel Kitchen REST API.

    Parameters
    ----------
    token:
        API token string, e.g. ``"Token abc123"``.  If it does not start
        with ``"Token "`` the prefix is added automatically.
    base_url:
        API root URL.  Defaults to ``https://api.controlpanel.kitchen``.
    timeout:
        Default request timeout in seconds.
    organization_host:
        Optional host/slug sent as ``X-Organization-Host`` for multi-tenant
        endpoints.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str = "https://api.controlpanel.kitchen",
        timeout: float = 30.0,
        organization_host: str | None = None,
    ) -> None:
        if token and not token.startswith("Token "):
            token = f"Token {token}"

        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = token
        if organization_host:
            headers["X-Organization-Host"] = organization_host

        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
        )

        # Initialise all generated endpoint cache slots to None
        self._init_endpoints()

    # ------------------------------------------------------------------
    # Alternative constructor
    # ------------------------------------------------------------------

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ControlPanelKitchenClient":
        """Create a client from a :class:`~cpk_sdk.client.settings.Settings` object.

        If *settings* is ``None``, settings are loaded from environment
        variables / ``.env`` file automatically.
        """
        s = settings or Settings()
        return cls(
            token=s.token,
            base_url=s.base_url,
            timeout=s.timeout,
            organization_host=s.organization_host,
        )

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ControlPanelKitchenClient":
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._http.__aexit__(*args)

    async def aclose(self) -> None:
        """Explicitly close the underlying HTTP session."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Low-level request helpers
    # ------------------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an authenticated HTTP request and raise on non-2xx responses."""
        response = await self._http.request(
            method,
            path,
            json=json,
            params=params,
            data=data,
            **kwargs,
        )
        raise_for_status(response)
        return response

    async def get(self, path: str, *, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        resp = await self.request("GET", path, params=params, **kw)
        return resp.json()

    async def post(self, path: str, *, json: Any = None, **kw: Any) -> Any:
        resp = await self.request("POST", path, json=json, **kw)
        return resp.json() if resp.content else None

    async def put(self, path: str, *, json: Any = None, **kw: Any) -> Any:
        resp = await self.request("PUT", path, json=json, **kw)
        return resp.json()

    async def patch(self, path: str, *, json: Any = None, **kw: Any) -> Any:
        resp = await self.request("PATCH", path, json=json, **kw)
        return resp.json()

    async def delete(self, path: str, **kw: Any) -> None:
        await self.request("DELETE", path, **kw)
