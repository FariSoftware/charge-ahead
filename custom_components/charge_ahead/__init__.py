"""Charge Ahead: charge the car in time for the next calendar trip."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .services import async_setup_services
from .target import PlanTarget, async_build_target

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type ChargeAheadConfigEntry = ConfigEntry[PlanTarget]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ChargeAheadConfigEntry) -> bool:
    """Set up Charge Ahead from a config entry."""
    entry.runtime_data = await async_build_target(
        hass, entry.title, dict(entry.options)
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ChargeAheadConfigEntry
) -> bool:
    """Unload a config entry."""
    return True
