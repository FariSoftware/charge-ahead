"""Fixtures for Charge Ahead tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_ahead.const import (
    CONF_CALENDAR_ENTITY,
    CONF_CAPACITY_KWH,
    CONF_CONSUMPTION,
    CONF_DEPARTURE_BUFFER,
    CONF_GOOGLE_ENTRY,
    CONF_RESERVE_PERCENT,
    CONF_ROUTING_PROVIDER,
    DOMAIN,
)

CALENDAR = "calendar.car"

BASE_OPTIONS: dict[str, Any] = {
    "name": "Elroq",
    CONF_CALENDAR_ENTITY: CALENDAR,
    CONF_ROUTING_PROVIDER: "google",
    CONF_GOOGLE_ENTRY: "google_entry",
    CONF_CAPACITY_KWH: 56.0,
    CONF_CONSUMPTION: 15.5,
    CONF_DEPARTURE_BUFFER: 15,
    CONF_RESERVE_PERCENT: 20,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


@pytest.fixture
def calendar_events(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Register calendar.get_events; the returned list is the calendar content."""
    events: list[dict[str, Any]] = []

    async def _get_events(call: ServiceCall) -> dict[str, Any]:
        entity_id = call.data["entity_id"]
        return {entity_id: {"events": list(events)}}

    hass.services.async_register(
        "calendar", "get_events", _get_events, supports_response=SupportsResponse.ONLY
    )
    return events


@pytest.fixture
def routes(hass: HomeAssistant) -> dict[str, tuple[float, float]]:
    """Register google_travel_time.get_travel_times.

    The returned dict maps destination -> (distance_km, duration_min). Unknown
    destinations fail like the real integration does.
    """
    known: dict[str, tuple[float, float]] = {}
    calls: list[str] = []

    async def _get_travel_times(call: ServiceCall) -> dict[str, Any]:
        destination = call.data["destination"]
        calls.append(destination)
        if destination not in known:
            raise HomeAssistantError("An error occurred while retrieving data")
        distance_km, duration_min = known[destination]
        return {
            "routes": [
                {
                    "duration": duration_min * 60,
                    "distance_meters": distance_km * 1000,
                }
            ]
        }

    hass.services.async_register(
        "google_travel_time",
        "get_travel_times",
        _get_travel_times,
        supports_response=SupportsResponse.ONLY,
    )
    known["__calls__"] = calls  # type: ignore[assignment]
    return known


@pytest.fixture
def setup_entry(hass: HomeAssistant, calendar_events, routes) -> Callable[..., Any]:
    """Return a coroutine that sets up an entry with extra options."""

    async def _setup(**options: Any) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN, title="Elroq", options={**BASE_OPTIONS, **options}
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _setup
