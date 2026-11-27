"""Services for Charge Ahead.

apply_plan and clear_plan push a plan to the configured target by hand. They
exist to test a target before the planner runs, and stay useful for scripts.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DEPARTURE,
    ATTR_ENERGY_KWH,
    ATTR_TARGET_SOC,
    DOMAIN,
    SERVICE_APPLY_PLAN,
    SERVICE_CLEAR_PLAN,
)
from .target import ChargePlan, PlanTarget

ENTRY_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})

APPLY_PLAN_SCHEMA = ENTRY_SCHEMA.extend(
    {
        vol.Required(ATTR_TARGET_SOC): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        ),
        vol.Required(ATTR_DEPARTURE): cv.datetime,
        vol.Optional(ATTR_ENERGY_KWH): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }
)


def _get_target(hass: HomeAssistant, call: ServiceCall) -> PlanTarget:
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"entry_id": entry_id},
        )
    return entry.runtime_data


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services."""

    async def _apply_plan(call: ServiceCall) -> None:
        target = _get_target(hass, call)
        departure = call.data[ATTR_DEPARTURE]
        if departure.tzinfo is None:
            departure = departure.replace(tzinfo=dt_util.get_default_time_zone())
        plan = ChargePlan(
            target_soc=call.data[ATTR_TARGET_SOC],
            departure=departure,
            energy_kwh=call.data.get(ATTR_ENERGY_KWH),
        )
        await target.async_apply(plan, call.context)

    async def _clear_plan(call: ServiceCall) -> None:
        await _get_target(hass, call).async_clear(call.context)

    hass.services.async_register(
        DOMAIN, SERVICE_APPLY_PLAN, _apply_plan, schema=APPLY_PLAN_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_PLAN, _clear_plan, schema=ENTRY_SCHEMA
    )
