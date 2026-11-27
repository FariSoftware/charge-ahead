"""Sensors exposing the current charging plan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ChargeAheadConfigEntry
from .const import DOMAIN, PlanStatus
from .coordinator import ChargeAheadCoordinator, ChargeAheadData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ChargeAheadSensorDescription(SensorEntityDescription):
    """Describes a Charge Ahead sensor."""

    value_fn: Callable[[ChargeAheadData], Any]
    attrs_fn: Callable[[ChargeAheadData], dict[str, Any]] | None = None


def _departure(data: ChargeAheadData) -> datetime | None:
    return data.plan.departure if data.plan else None


SENSORS: tuple[ChargeAheadSensorDescription, ...] = (
    ChargeAheadSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in PlanStatus],
        value_fn=lambda data: data.status.value,
        attrs_fn=lambda data: {
            "warnings": sorted(w.value for w in data.warnings),
            "error": data.error,
            "consumption_kwh_per_100km": data.consumption_kwh_per_100km,
            "chained_trips": data.plan.chained_trips if data.plan else 0,
        },
    ),
    ChargeAheadSensorDescription(
        key="departure",
        translation_key="departure",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_departure,
    ),
    ChargeAheadSensorDescription(
        key="target_soc",
        translation_key="target_soc",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.plan.target_soc if data.plan else None,
    ),
    ChargeAheadSensorDescription(
        key="energy",
        translation_key="energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda data: data.plan.energy_kwh if data.plan else None,
    ),
    ChargeAheadSensorDescription(
        key="distance",
        translation_key="distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=lambda data: round(data.route.distance_km, 1) if data.route else None,
    ),
    ChargeAheadSensorDescription(
        key="travel_time",
        translation_key="travel_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda data: (
            round(data.route.duration.total_seconds() / 60) if data.route else None
        ),
    ),
    ChargeAheadSensorDescription(
        key="trip",
        translation_key="trip",
        value_fn=lambda data: (data.trip.summary or None) if data.trip else None,
        attrs_fn=lambda data: {
            "start": data.trip.start.isoformat() if data.trip else None,
            "location": data.trip.location if data.trip else None,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargeAheadConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ChargeAheadSensor(coordinator, entry, description) for description in SENSORS
    )


class ChargeAheadSensor(CoordinatorEntity[ChargeAheadCoordinator], SensorEntity):
    """A Charge Ahead sensor."""

    _attr_has_entity_name = True
    entity_description: ChargeAheadSensorDescription

    def __init__(
        self,
        coordinator: ChargeAheadCoordinator,
        entry: ChargeAheadConfigEntry,
        description: ChargeAheadSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
