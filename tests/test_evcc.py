"""Tests for the evcc target."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest

from custom_components.charge_ahead.const import (
    CONF_CALENDAR_ENTITY,
    CONF_EVCC_VEHICLE,
    CONF_ROUTING_PROVIDER,
    CONF_TARGET_TYPE,
    DOMAIN,
)

NOW = datetime(2026, 11, 27, 9, 0, tzinfo=dt_util.UTC)


@pytest.fixture(autouse=True)
def _frozen(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


@pytest.fixture
def evcc(hass: HomeAssistant) -> dict[str, Any]:
    """Fake evcc_intg services; set state['set_error'] to make set fail."""
    state: dict[str, Any] = {"set": [], "del": [], "set_error": None}

    async def _set(call: ServiceCall) -> dict[str, Any]:
        state["set"].append(dict(call.data))
        if state["set_error"]:
            return {"error": state["set_error"]}
        return {"success": "true"}

    async def _del(call: ServiceCall) -> dict[str, Any]:
        state["del"].append(dict(call.data))
        return {"error": "NO or EMPTY response"}

    hass.services.async_register(
        "evcc_intg",
        "set_vehicle_plan",
        _set,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        "evcc_intg",
        "del_vehicle_plan",
        _del,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return state


def _event(hours: float, location: str) -> dict:
    start = NOW + timedelta(hours=hours)
    return {
        "start": start.isoformat(),
        "end": (start + timedelta(hours=1)).isoformat(),
        "summary": "Trip",
        "location": location,
    }


async def test_flow_offers_evcc_and_detects_vehicle(hass: HomeAssistant, evcc) -> None:
    """With evcc installed, the menu offers evcc and preselects its vehicle."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "select",
        "evcc_intg",
        "evcc_intg.evcc_garage_vehicle_name",
        suggested_object_id="evcc_garage_vehicle_name",
    )
    hass.states.async_set(
        "select.evcc_garage_vehicle_name",
        "db:13",
        {
            "options": ["null", "db:13"],
            "vehicle": {"evccName": "db:13", "name": "Elroq"},
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    flow_id = result["flow_id"]
    await hass.config_entries.flow.async_configure(
        flow_id, {"name": "Elroq", CONF_CALENDAR_ENTITY: "calendar.car"}
    )
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_ROUTING_PROVIDER: "waze"}
    )
    await hass.config_entries.flow.async_configure(flow_id, {})
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"][0] == "target_evcc"

    result = await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": "target_evcc"}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_TARGET_TYPE] == "evcc"
    assert result["options"][CONF_EVCC_VEHICLE] == "db:13"


async def test_evcc_target_sets_and_clears_plan(
    hass: HomeAssistant, setup_entry, calendar_events, routes, evcc
) -> None:
    """The plan goes to evcc in local time; a gone trip deletes it."""
    calendar_events.append(_event(5, "Stuttgart"))
    routes["Stuttgart"] = (30, 30)

    entry = await setup_entry(**{CONF_TARGET_TYPE: "evcc", CONF_EVCC_VEHICLE: "db:13"})

    departure = NOW + timedelta(hours=5) - timedelta(minutes=45)
    assert evcc["set"] == [
        {
            "vehicle": "db:13",
            "soc": int(hass.states.get("sensor.elroq_target_soc").state),
            "startdate": dt_util.as_local(departure).strftime("%Y-%m-%d %H:%M:%S"),
        }
    ]

    calendar_events.clear()
    await entry.runtime_data.coordinator.async_refresh()

    assert evcc["del"] == [{"vehicle": "db:13"}]
    assert hass.states.get("sensor.elroq_status").state == "no_trip"


async def test_evcc_error_response_is_a_failure(
    hass: HomeAssistant, setup_entry, calendar_events, routes, evcc
) -> None:
    """An error in evcc's response data sets target_failed."""
    calendar_events.append(_event(5, "Stuttgart"))
    routes["Stuttgart"] = (30, 30)
    evcc["set_error"] = "time data does not match format"

    await setup_entry(**{CONF_TARGET_TYPE: "evcc", CONF_EVCC_VEHICLE: "db:13"})

    status = hass.states.get("sensor.elroq_status")
    assert status.state == "target_failed"
    assert "time data" in status.attributes["error"]
