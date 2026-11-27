"""Constants for Charge Ahead."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "charge_ahead"

CONF_CALENDAR_ENTITY: Final = "calendar_entity"
CONF_TARGET_TYPE: Final = "target_type"
CONF_TARGET_SOC_ENTITY: Final = "target_soc_entity"
CONF_DEPARTURE_ENTITY: Final = "departure_entity"
CONF_SET_ACTION: Final = "set_action"
CONF_CLEAR_ACTION: Final = "clear_action"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_TARGET_SOC: Final = "target_soc"
ATTR_DEPARTURE: Final = "departure"
ATTR_ENERGY_KWH: Final = "energy_kwh"

SERVICE_APPLY_PLAN: Final = "apply_plan"
SERVICE_CLEAR_PLAN: Final = "clear_plan"


class TargetType(StrEnum):
    """Where a computed charging plan is written to."""

    NONE = "none"
    ENTITIES = "entities"
    ACTION = "action"
