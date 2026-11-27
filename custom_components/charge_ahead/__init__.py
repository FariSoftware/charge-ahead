"""Charge Ahead: charge the car in time for the next calendar trip."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import STORAGE_VERSION, ChargeAheadCoordinator
from .services import async_setup_services
from .target import PlanTarget, async_build_target

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.BUTTON, Platform.SENSOR]


@dataclass(slots=True)
class ChargeAheadRuntimeData:
    """Objects owned by a config entry."""

    target: PlanTarget
    coordinator: ChargeAheadCoordinator


type ChargeAheadConfigEntry = ConfigEntry[ChargeAheadRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ChargeAheadConfigEntry) -> bool:
    """Set up Charge Ahead from a config entry."""
    target = await async_build_target(hass, entry.title, dict(entry.options))
    coordinator = ChargeAheadCoordinator(hass, entry, target)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_track_calendar()
    entry.runtime_data = ChargeAheadRuntimeData(target=target, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_entry(
    hass: HomeAssistant, entry: ChargeAheadConfigEntry
) -> None:
    """Remove stored state when the entry is deleted."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def async_unload_entry(
    hass: HomeAssistant, entry: ChargeAheadConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
