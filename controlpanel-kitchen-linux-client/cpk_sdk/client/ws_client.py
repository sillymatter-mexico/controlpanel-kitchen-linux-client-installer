"""WebSocket client for the ControlPanel Kitchen real-time API.

Usage
-----
    async with CPKWebSocketClient(token="Token abc123") as conn:
        conn = ws.commander(client_name="linux-client-v1")
        async with conn:
            async for event in conn.listen():
                print(event["event"], event)

Or driven by environment variables (prefix ``CPK_``):

    from cpk_sdk.client.settings import Settings
    ws = CPKWebSocketClient.from_settings()
    async with ws.live_feed(restaurant_uuid="...") as conn:
        conn.on("restaurant_order_created", handle_order)
        await conn.run()

Channel factory methods (generated — re-run ``make generate-ws`` to update):

    ws.commander(*, client_name=None)                    → CommanderConnection
    ws.notifications()                                   → NotificationsConnection
    ws.chat(room_name)                                   → ChatConnection
    ws.live_feed(restaurant_uuid, *, ...)                → LiveFeedConnection
    ws.map(restaurant_uuid, *, ...)                      → MapConnection
    ws.public_tracker(*, tracking_code, username=None)   → PublicTrackerConnection
"""

from __future__ import annotations

from cpk_sdk.client.settings import Settings
from cpk_sdk.client.ws_base import _BaseWSConnection  # re-exported
from cpk_sdk.client.ws_channels import _GeneratedChannelsMixin

__all__ = ["CPKWebSocketClient", "_BaseWSConnection"]


class CPKWebSocketClient(_GeneratedChannelsMixin):
    """WebSocket client for the ControlPanel Kitchen real-time API.

    Parameters
    ----------
    token:
        API token string, e.g. ``"Token abc123"``.  If it does not start
        with ``"Token "`` the prefix is added automatically.
    base_url:
        WebSocket root URL.  Defaults to ``wss://api.controlpanel.kitchen``.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str = "wss://api.controlpanel.kitchen",
    ) -> None:
        if token and not token.startswith("Token "):
            token = f"Token {token}"
        self._token = token
        self._base_url = base_url.rstrip("/")

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "CPKWebSocketClient":
        """Create a client from a :class:`~cpk_sdk.client.settings.Settings` object.

        If *settings* is ``None``, values are loaded from environment
        variables / ``.env`` file automatically.
        """
        s = settings or Settings()
        url = s.base_url.replace("https://", "wss://").replace("http://", "ws://")
        return cls(token=s.token, base_url=url)
