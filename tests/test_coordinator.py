"""End-to-end tests: calendar, routing, planning, target and notifications."""

from __future__ import annotations

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.charge_ahead.const import (
    CONF_CLEAR_ACTION,
    CONF_NOTIFY,
    CONF_RANGE_ENTITY,
    CONF_SET_ACTION,
    CONF_SOC_ENTITY,
    CONF_SOC_LIMIT_ENTITY,
    CONF_TARGET_TYPE,
)
from custom_components.charge_ahead.coordinator import parse_event

NOW = datetime(2026, 11, 27, 9, 0, tzinfo=dt_util.get_default_time_zone())

ACTION_OPTIONS = {
    CONF_TARGET_TYPE: "action",
    CONF_SET_ACTION: [
        {
            "action": "test.set_plan",
            "data": {"soc": "{{ target_soc }}", "time": "{{ departure_local }}"},
        }
    ],
    CONF_CLEAR_ACTION: [{"action": "test.clear_plan"}],
}


@pytest.fixture(autouse=True)
def _frozen(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


def _event(hours: float, location: str | None, summary: str = "Trip") -> dict:
    event = {
        "start": (NOW + timedelta(hours=hours)).isoformat(),
        "end": (NOW + timedelta(hours=hours + 1)).isoformat(),
        "summary": summary,
    }
    if location is not None:
        event["location"] = location
    return event


def _state(hass: HomeAssistant, key: str) -> str:
    return hass.states.get(f"sensor.elroq_{key}").state


async def _refresh(hass: HomeAssistant, entry, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(minutes=16))
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_no_trip(hass: HomeAssistant, setup_entry) -> None:
    """Without trips the status is no_trip and plan sensors are unknown."""
    await setup_entry()

    assert _state(hass, "status") == "no_trip"
    assert _state(hass, "target_soc") == "unknown"


async def test_trip_is_planned_and_applied(
    hass: HomeAssistant, setup_entry, calendar_events, routes
) -> None:
    """A trip is routed, planned and written once."""
    calendar_events.append(_event(5, "Stuttgart", "Meeting"))
    calendar_events.append(_event(3, None, "Call"))
    routes["Stuttgart"] = (100, 60)
    calls = async_mock_service(hass, "test", "set_plan")

    await setup_entry(**ACTION_OPTIONS)

    assert _state(hass, "status") == "planned"
    assert _state(hass, "next_trip") == "Meeting"
    assert _state(hass, "distance") == "100.0"
    assert _state(hass, "travel_time") == "60"
    # 2 x 100 km x 15.5 kWh/100 km = 31 kWh = 55.4 % of 56 kWh, + 20 % = 76 %
    assert _state(hass, "target_soc") == "76"
    departure = NOW + timedelta(hours=5) - timedelta(minutes=75)
    assert dt_util.parse_datetime(_state(hass, "departure")) == departure

    assert len(calls) == 1
    assert calls[0].data == {
        "soc": 76,
        "time": dt_util.as_local(departure).strftime("%Y-%m-%d %H:%M:%S"),
    }


async def test_unchanged_plan_is_not_rewritten(
    hass: HomeAssistant,
    setup_entry,
    calendar_events,
    routes,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A refresh with the same plan does not run the action again."""
    calendar_events.append(_event(5, "Stuttgart"))
    routes["Stuttgart"] = (100, 60)
    calls = async_mock_service(hass, "test", "set_plan")
    entry = await setup_entry(**ACTION_OPTIONS)

    await _refresh(hass, entry, freezer)

    assert len(calls) == 1


async def test_cancelled_trip_clears_plan(
    hass: HomeAssistant,
    setup_entry,
    calendar_events,
    routes,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A trip removed before departure runs the clear action."""
    calendar_events.append(_event(5, "Stuttgart"))
    routes["Stuttgart"] = (100, 60)
    async_mock_service(hass, "test", "set_plan")
    clear_calls = async_mock_service(hass, "test", "clear_plan")
    entry = await setup_entry(**ACTION_OPTIONS)

    calendar_events.clear()
    await _refresh(hass, entry, freezer)

    assert _state(hass, "status") == "no_trip"
    assert len(clear_calls) == 1


async def test_multiline_location_falls_back_to_address(
    hass: HomeAssistant, setup_entry, calendar_events, routes
) -> None:
    """Apple-style 'place\\naddress' locations are routed by the address line."""
    calendar_events.append(
        _event(5, "Lise Meitner Gymnasium\nTriberger Straße 20, 71034 Böblingen")
    )
    routes["Triberger Straße 20, 71034 Böblingen"] = (6.1, 10)

    await setup_entry()

    assert _state(hass, "status") == "planned"
    assert routes["__calls__"] == [
        "Lise Meitner Gymnasium, Triberger Straße 20, 71034 Böblingen",
        "Triberger Straße 20, 71034 Böblingen",
    ]


async def test_routing_failure_notifies_once(
    hass: HomeAssistant,
    setup_entry,
    calendar_events,
    routes,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An unknown location sets routing_failed and notifies once."""
    calendar_events.append(_event(5, "Nowhere"))
    notify_calls = async_mock_service(hass, "notify", "mobile_app_phone")

    entry = await setup_entry(**{CONF_NOTIFY: "notify.mobile_app_phone"})
    await _refresh(hass, entry, freezer)

    assert _state(hass, "status") == "routing_failed"
    assert len(notify_calls) == 1
    assert "Nowhere" in notify_calls[0].data["message"]


async def test_above_limit_warns(
    hass: HomeAssistant, setup_entry, calendar_events, routes
) -> None:
    """A target above the charge limit is applied and a warning is sent."""
    hass.states.async_set("sensor.limit", "80", {"friendly_name": "evcc limit"})
    calendar_events.append(_event(8, "Munich"))
    routes["Munich"] = (120, 90)
    set_calls = async_mock_service(hass, "test", "set_plan")
    notify_calls = async_mock_service(hass, "notify", "mobile_app_phone")

    await setup_entry(
        **ACTION_OPTIONS,
        **{
            CONF_SOC_LIMIT_ENTITY: "sensor.limit",
            CONF_NOTIFY: "notify.mobile_app_phone",
        },
    )

    assert _state(hass, "status") == "planned"
    assert hass.states.get("sensor.elroq_status").attributes["warnings"] == [
        "above_limit"
    ]
    assert len(set_calls) == 1
    assert len(notify_calls) == 1
    assert "evcc limit" in notify_calls[0].data["message"]


async def test_departure_passed_is_not_applied(
    hass: HomeAssistant, setup_entry, calendar_events, routes
) -> None:
    """If the departure has already passed, nothing is written."""
    calendar_events.append(_event(0.5, "Stuttgart"))
    routes["Stuttgart"] = (30, 60)
    calls = async_mock_service(hass, "test", "set_plan")

    await setup_entry(**ACTION_OPTIONS)

    assert _state(hass, "status") == "departure_passed"
    assert calls == []


async def test_aborted_action_sets_target_failed(
    hass: HomeAssistant, setup_entry, calendar_events, routes
) -> None:
    """A set action that stops with an error is reported as target_failed."""
    calendar_events.append(_event(5, "Stuttgart"))
    routes["Stuttgart"] = (30, 30)

    await setup_entry(
        **{
            CONF_TARGET_TYPE: "action",
            CONF_SET_ACTION: [{"stop": "rejected", "error": True}],
        }
    )

    assert _state(hass, "status") == "target_failed"


async def test_consumption_from_range(
    hass: HomeAssistant, setup_entry, calendar_events, routes
) -> None:
    """SoC and range entities override the fixed consumption."""
    hass.states.async_set("sensor.soc", "50")
    hass.states.async_set("sensor.range", "200")
    calendar_events.append(_event(5, "Stuttgart"))
    routes["Stuttgart"] = (100, 60)

    await setup_entry(
        **{CONF_SOC_ENTITY: "sensor.soc", CONF_RANGE_ENTITY: "sensor.range"}
    )

    # 56 kWh x 50 % / 200 km = 14 kWh/100 km; 28 kWh = 50 % + 20 % = 70 %
    assert _state(hass, "target_soc") == "70"
    status = hass.states.get("sensor.elroq_status")
    assert status.attributes["consumption_kwh_per_100km"] == 14.0


def test_parse_all_day_event() -> None:
    """All-day events are recognised and never count as trips."""
    trip = parse_event({"start": "2026-12-01", "summary": "Holiday", "location": "X"})
    assert trip is not None
    assert trip.all_day


async def test_plan_survives_reload_and_is_cleared(
    hass: HomeAssistant, setup_entry, calendar_events, routes
) -> None:
    """A plan written before a reload is cleared when its trip is gone after it."""
    calendar_events.append(_event(5, "Stuttgart"))
    routes["Stuttgart"] = (100, 60)
    async_mock_service(hass, "test", "set_plan")
    clear_calls = async_mock_service(hass, "test", "clear_plan")
    entry = await setup_entry(**ACTION_OPTIONS)

    calendar_events.clear()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert _state(hass, "status") == "no_trip"
    assert len(clear_calls) == 1
