"""Tests for the Charge Ahead config flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_ahead.const import (
    CONF_CALENDAR_ENTITY,
    CONF_DEPARTURE_ENTITY,
    CONF_SET_ACTION,
    CONF_TARGET_SOC_ENTITY,
    CONF_TARGET_TYPE,
    DOMAIN,
)

SET_ACTION = [
    {
        "action": "test.set_plan",
        "data": {"soc": "{{ target_soc }}", "time": "{{ departure }}"},
    }
]


async def _start_flow(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Elroq", CONF_CALENDAR_ENTITY: "calendar.car"},
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "target"
    return result["flow_id"]


async def test_flow_action_target(hass: HomeAssistant) -> None:
    """An action target stores the action sequence."""
    flow_id = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": "target_action"}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SET_ACTION: SET_ACTION}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Elroq"
    assert result["options"] == {
        "name": "Elroq",
        CONF_CALENDAR_ENTITY: "calendar.car",
        CONF_SET_ACTION: SET_ACTION,
        CONF_TARGET_TYPE: "action",
    }


async def test_flow_entities_target(hass: HomeAssistant) -> None:
    """An entity target stores both entities."""
    flow_id = await _start_flow(hass)
    await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": "target_entities"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_TARGET_SOC_ENTITY: "number.target_soc",
            CONF_DEPARTURE_ENTITY: "datetime.departure",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_TARGET_TYPE] == "entities"


async def test_flow_no_target(hass: HomeAssistant) -> None:
    """No target only records the target type."""
    flow_id = await _start_flow(hass)
    await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": "target_none"}
    )
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_TARGET_TYPE] == "none"


async def test_options_switch_target_drops_stale_keys(hass: HomeAssistant) -> None:
    """Switching from action to entities removes the action keys."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Elroq",
        options={
            "name": "Elroq",
            CONF_CALENDAR_ENTITY: "calendar.car",
            CONF_SET_ACTION: SET_ACTION,
            CONF_TARGET_TYPE: "action",
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CALENDAR_ENTITY: "calendar.car"}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "target_entities"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_TARGET_SOC_ENTITY: "number.target_soc",
            CONF_DEPARTURE_ENTITY: "datetime.departure",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_SET_ACTION not in entry.options
    assert entry.options[CONF_TARGET_TYPE] == "entities"
