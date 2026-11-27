"""Tests for the Charge Ahead config flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.charge_ahead.const import (
    CONF_CALENDAR_ENTITY,
    CONF_DEPARTURE_ENTITY,
    CONF_GOOGLE_ENTRY,
    CONF_NOTIFY,
    CONF_ROUTING_PROVIDER,
    CONF_SET_ACTION,
    CONF_TARGET_SOC_ENTITY,
    CONF_TARGET_TYPE,
    DOMAIN,
)

SET_ACTION = [
    {
        "action": "test.set_plan",
        "data": {"soc": "{{ target_soc }}", "time": "{{ departure_local }}"},
    }
]


async def _to_target_menu(hass: HomeAssistant, **planning) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    flow_id = result["flow_id"]
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"name": "Elroq", CONF_CALENDAR_ENTITY: "calendar.car"}
    )
    assert result["step_id"] == "routing"
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_ROUTING_PROVIDER: "waze"}
    )
    assert result["step_id"] == "vehicle"
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["step_id"] == "planning"
    result = await hass.config_entries.flow.async_configure(flow_id, planning)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "target"
    return flow_id


async def test_flow_action_target(hass: HomeAssistant) -> None:
    """A full flow with an action target stores all options."""
    flow_id = await _to_target_menu(hass)
    await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": "target_action"}
    )
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SET_ACTION: SET_ACTION}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Elroq"
    options = result["options"]
    assert options[CONF_SET_ACTION] == SET_ACTION
    assert options[CONF_TARGET_TYPE] == "action"
    assert options[CONF_ROUTING_PROVIDER] == "waze"
    assert options["capacity_kwh"] == 50.0
    assert options["reserve_percent"] == 20


async def test_google_requires_entry(hass: HomeAssistant) -> None:
    """Choosing Google without a config entry shows an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Elroq", CONF_CALENDAR_ENTITY: "calendar.car"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ROUTING_PROVIDER: "google"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "google_entry_required"}


async def test_notify_target_validated(hass: HomeAssistant) -> None:
    """An unknown notify target is rejected, a known action accepted."""
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
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_NOTIFY: "notify.nope"}
    )
    assert result["errors"] == {"base": "notify_not_found"}

    async_mock_service(hass, "notify", "mobile_app_phone")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_NOTIFY: "notify.mobile_app_phone"}
    )
    assert result["type"] is FlowResultType.MENU


async def test_flow_no_target(hass: HomeAssistant) -> None:
    """No target only records the target type."""
    flow_id = await _to_target_menu(hass)
    await hass.config_entries.flow.async_configure(
        flow_id, {"next_step_id": "target_none"}
    )
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_TARGET_TYPE] == "none"


async def test_options_switch_target_drops_stale_keys(
    hass: HomeAssistant, setup_entry
) -> None:
    """Switching from action to entities removes the action keys."""
    entry = await setup_entry(
        **{CONF_TARGET_TYPE: "action", CONF_SET_ACTION: SET_ACTION}
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await hass.config_entries.options.async_configure(
        flow_id, {CONF_CALENDAR_ENTITY: "calendar.car"}
    )
    assert result["step_id"] == "routing"
    result = await hass.config_entries.options.async_configure(
        flow_id, {CONF_ROUTING_PROVIDER: "google", CONF_GOOGLE_ENTRY: "google_entry"}
    )
    result = await hass.config_entries.options.async_configure(flow_id, {})
    result = await hass.config_entries.options.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "target_entities"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id,
        {
            CONF_TARGET_SOC_ENTITY: "number.target_soc",
            CONF_DEPARTURE_ENTITY: "datetime.departure",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_SET_ACTION not in entry.options
    assert entry.options[CONF_TARGET_TYPE] == "entities"
