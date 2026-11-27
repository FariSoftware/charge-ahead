"""Button to write the current plan to the target again."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ChargeAheadConfigEntry
from .const import DOMAIN
from .coordinator import ChargeAheadCoordinator

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargeAheadConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button."""
    async_add_entities([ReapplyButton(entry.runtime_data.coordinator, entry)])


class ReapplyButton(CoordinatorEntity[ChargeAheadCoordinator], ButtonEntity):
    """Write the current plan to the target even if it did not change.

    Useful when the plan was removed on the target side, for example by
    deleting it in the charge controller.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "reapply"

    def __init__(
        self, coordinator: ChargeAheadCoordinator, entry: ChargeAheadConfigEntry
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_reapply"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        """Write the plan again."""
        await self.coordinator.async_reapply()
