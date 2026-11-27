"""Tests for the Charge Ahead services and plan targets."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.charge_ahead.const import (
    CONF_CLEAR_ACTION,
    CONF_DEPARTURE_ENTITY,
    CONF_SET_ACTION,
    CONF_TARGET_SOC_ENTITY,
    CONF_TARGET_TYPE,
    DOMAIN,
)

DEPARTURE = "2026-12-01T07:30:00+01:00"


async def test_action_target_renders_variables(
    hass: HomeAssistant, setup_entry
) -> None:
    """The set action receives target_soc, departure and energy_kwh."""
    calls = async_mock_service(hass, "test", "set_plan")
    entry = await setup_entry(
        **{
            CONF_TARGET_TYPE: "action",
            CONF_SET_ACTION: [
                {
                    "action": "test.set_plan",
                    "data": {
                        "soc": "{{ target_soc }}",
                        "time": "{{ departure }}",
                        "local": "{{ departure_local }}",
                        "kwh": "{{ energy_kwh }}",
                    },
                }
            ],
        },
    )

    await hass.services.async_call(
        DOMAIN,
        "apply_plan",
        {
            "config_entry_id": entry.entry_id,
            "target_soc": 65,
            "departure": DEPARTURE,
            "energy_kwh": 12.5,
        },
        blocking=True,
    )

    assert len(calls) == 1
    assert calls[0].data["soc"] == 65
    assert dt_util.parse_datetime(calls[0].data["time"]) == datetime.fromisoformat(
        DEPARTURE
    )
    assert calls[0].data["kwh"] == 12.5
    assert calls[0].data["local"] == dt_util.as_local(
        datetime.fromisoformat(DEPARTURE)
    ).strftime("%Y-%m-%d %H:%M:%S")


async def test_action_target_clear(hass: HomeAssistant, setup_entry) -> None:
    """clear_plan runs the clear action."""
    calls = async_mock_service(hass, "test", "clear_plan")
    entry = await setup_entry(
        **{
            CONF_TARGET_TYPE: "action",
            CONF_SET_ACTION: [{"action": "test.set_plan"}],
            CONF_CLEAR_ACTION: [{"action": "test.clear_plan"}],
        },
    )

    await hass.services.async_call(
        DOMAIN, "clear_plan", {"config_entry_id": entry.entry_id}, blocking=True
    )
    assert len(calls) == 1


async def test_entity_target(hass: HomeAssistant, setup_entry) -> None:
    """The entity target calls number.set_value and datetime.set_value."""
    number_calls = async_mock_service(hass, "number", "set_value")
    datetime_calls = async_mock_service(hass, "datetime", "set_value")
    entry = await setup_entry(
        **{
            CONF_TARGET_TYPE: "entities",
            CONF_TARGET_SOC_ENTITY: "number.target_soc",
            CONF_DEPARTURE_ENTITY: "datetime.departure",
        },
    )

    await hass.services.async_call(
        DOMAIN,
        "apply_plan",
        {"config_entry_id": entry.entry_id, "target_soc": 70, "departure": DEPARTURE},
        blocking=True,
    )

    assert number_calls[0].data == {"entity_id": "number.target_soc", "value": 70}
    assert datetime_calls[0].data["entity_id"] == "datetime.departure"
    assert datetime_calls[0].data["datetime"] == datetime.fromisoformat(DEPARTURE)


async def test_unknown_entry(hass: HomeAssistant, setup_entry) -> None:
    """An unknown entry id raises a validation error."""
    await setup_entry(**{CONF_TARGET_TYPE: "none"})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "apply_plan",
            {"config_entry_id": "nope", "target_soc": 50, "departure": DEPARTURE},
            blocking=True,
        )
