"""Minimal async client for api.weather.gov."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import API_BASE, USER_AGENT

TIMEOUT = aiohttp.ClientTimeout(total=20)
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}


class NWSApiError(Exception):
    """Generic API failure."""


class NWSInvalidLocation(NWSApiError):
    """The API rejected the point (usually outside NWS coverage)."""


class NWSClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            async with self._session.get(
                f"{API_BASE}{path}", params=params, headers=HEADERS, timeout=TIMEOUT
            ) as resp:
                if resp.status in (400, 404):
                    raise NWSInvalidLocation(f"HTTP {resp.status}: {await resp.text()}")
                if resp.status >= 400:
                    raise NWSApiError(f"HTTP {resp.status} from {path}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise NWSApiError(f"{type(err).__name__}: {err}") from err

    async def active_alerts(self, lat: float, lon: float) -> list[dict[str, Any]]:
        """Active alerts whose polygon or zones cover the point."""
        data = await self._get(
            "/alerts/active",
            {"point": f"{lat:.4f},{lon:.4f}", "status": "actual"},
        )
        return data.get("features") or []

    async def event_types(self) -> list[str]:
        data = await self._get("/alerts/types")
        return list(data.get("eventTypes") or [])
