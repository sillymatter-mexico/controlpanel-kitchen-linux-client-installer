"""Base WebSocket connection class shared by all channel implementations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect

if TYPE_CHECKING:
    from cpk_sdk.client.ws_client import CPKWebSocketClient


class _BaseWSConnection:
    """Base for a typed WebSocket channel connection.

    Use as an async context manager::

        async with client.commander(client_name="my-client") as conn:
            async for event in conn.listen():
                print(event)

    Or register handlers and call :meth:`run`::

        async with client.live_feed(restaurant_uuid="...") as conn:
            conn.on("restaurant_order_created", handle_order)
            await conn.run()
    """

    #: AsyncAPI channel path, e.g. ``"ws/commander/"``.
    CHANNEL: str = ""
    #: Set to True for channels that require no auth token.
    NO_AUTH: bool = False

    def __init__(self, client: "CPKWebSocketClient", **path_params: str) -> None:
        self._client = client
        self._path_params = path_params
        self._query_params: dict[str, str] = {}
        self._ws: ClientConnection | None = None
        self._ws_cm: connect | None = None
        self._handlers: dict[str, list[Callable[..., Any]]] = {}

    # ------------------------------------------------------------------
    # URL construction
    # ------------------------------------------------------------------

    def _build_url(self) -> str:
        channel = self.CHANNEL.format(**self._path_params)
        url = f"{self._client._base_url}/{channel}"
        qs: dict[str, str] = {}
        if not self.NO_AUTH:
            token = self._client._token
            if token:
                qs["token"] = token.removeprefix("Token ").strip()
        qs.update(self._query_params)
        if qs:
            url += "?" + urlencode(qs)
        return url

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        self._ws_cm = connect(self._build_url())
        self._ws = await self._ws_cm.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._ws_cm is not None:
            await self._ws_cm.__aexit__(exc_type, exc_val, exc_tb)

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        """Yield parsed JSON messages received from the server."""
        if self._ws is None:
            raise RuntimeError("Not connected — use 'async with' to open the connection.")
        async for raw in self._ws:
            if isinstance(raw, bytes):
                raw = raw.decode()
            yield json.loads(raw)

    async def send(self, data: dict[str, Any]) -> None:
        """Send a JSON-encoded message to the server."""
        if self._ws is None:
            raise RuntimeError("Not connected — use 'async with' to open the connection.")
        await self._ws.send(json.dumps(data))

    # ------------------------------------------------------------------
    # Event dispatch
    # ------------------------------------------------------------------

    def on(self, event_type: str, handler: Callable[..., Any]) -> Self:
        """Register *handler* for messages whose ``type`` or ``event`` field equals *event_type*.

        Handlers may be plain functions or coroutines.  Returns ``self`` for
        chaining::

            conn.on("restaurant_order_created", handle_order)
                .on("restaurant_order_updated", handle_order)
        """
        self._handlers.setdefault(event_type, []).append(handler)
        return self

    async def run(self) -> None:
        """Consume messages indefinitely, dispatching each to registered handlers.

        Blocks until the connection is closed.  Unhandled event types are silently
        ignored.
        """
        async for event in self.listen():
            event_type = event.get("type") or event.get("event") or ""
            for handler in self._handlers.get(event_type, []):
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
