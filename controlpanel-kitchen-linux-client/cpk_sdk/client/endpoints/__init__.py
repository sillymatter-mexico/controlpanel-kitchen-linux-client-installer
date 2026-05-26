"""Endpoint namespace base class."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cpk_sdk.client.http_client import ControlPanelKitchenClient


class BaseEndpoints:
    def __init__(self, client: "ControlPanelKitchenClient") -> None:
        self._client = client
