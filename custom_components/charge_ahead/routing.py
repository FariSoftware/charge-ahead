"""Routing through the Google Maps or Waze travel time integrations."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import RoutingProvider
from .planner import Route

_LOGGER = logging.getLogger(__name__)


class RoutingError(Exception):
    """No route could be determined."""


def location_candidates(location: str) -> list[str]:
    """Return destination strings to try, best first.

    Calendar apps often store a place name and the address on separate lines
    (Apple: "Lise Meitner Gymnasium\\nTriberger Straße 20, 71034 Böblingen").
    Try the joined form first, then the last line, which usually is the address.
    """
    lines = [line.strip() for line in location.splitlines() if line.strip()]
    if not lines:
        return []
    candidates = [", ".join(lines)]
    if len(lines) > 1:
        candidates.append(lines[-1])
    return candidates


def parse_google(response: dict[str, Any]) -> Route:
    """Parse google_travel_time.get_travel_times response data."""
    routes = response.get("routes") or []
    if not routes:
        raise RoutingError("no route")
    route = routes[0]
    return Route(
        distance_km=route["distance_meters"] / 1000,
        duration=timedelta(seconds=route["duration"]),
    )


def parse_waze(response: dict[str, Any]) -> Route:
    """Parse waze_travel_time.get_travel_times response data (metric units)."""
    routes = [r for r in response.get("routes") or [] if r.get("duration")]
    if not routes:
        raise RoutingError("no route")
    route = min(routes, key=lambda r: r["duration"])
    return Route(
        distance_km=float(route["distance"]),
        duration=timedelta(minutes=route["duration"]),
    )


async def async_get_route(
    hass: HomeAssistant,
    provider: RoutingProvider,
    origin: str,
    destination: str,
    *,
    google_entry_id: str | None = None,
    waze_region: str = "eu",
) -> Route:
    """Return the route from origin to destination."""
    if provider is RoutingProvider.GOOGLE:
        domain = "google_travel_time"
        data = {
            "config_entry_id": google_entry_id,
            "origin": origin,
            "destination": destination,
            "mode": "driving",
            "units": "metric",
        }
        parser = parse_google
    else:
        domain = "waze_travel_time"
        data = {
            "origin": origin,
            "destination": destination,
            "region": waze_region,
            "units": "metric",
        }
        parser = parse_waze

    try:
        response = await hass.services.async_call(
            domain,
            "get_travel_times",
            data,
            blocking=True,
            return_response=True,
        )
    except (HomeAssistantError, ValueError) as err:
        raise RoutingError(str(err)) from err
    return parser(response or {})


async def async_route_location(
    hass: HomeAssistant,
    provider: RoutingProvider,
    origin: str,
    location: str,
    **kwargs: Any,
) -> Route:
    """Route to a calendar location, trying all candidate spellings."""
    last_error: RoutingError | None = None
    for destination in location_candidates(location):
        try:
            return await async_get_route(hass, provider, origin, destination, **kwargs)
        except RoutingError as err:
            _LOGGER.debug("Routing to %r failed: %s", destination, err)
            last_error = err
    raise last_error or RoutingError("empty location")
