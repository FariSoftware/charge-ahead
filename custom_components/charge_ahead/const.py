"""Constants for Charge Ahead."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "charge_ahead"

# Trip source
CONF_CALENDAR_ENTITY: Final = "calendar_entity"

# Routing
CONF_ROUTING_PROVIDER: Final = "routing_provider"
CONF_GOOGLE_ENTRY: Final = "google_config_entry"
CONF_WAZE_REGION: Final = "waze_region"
CONF_HOME_ZONE: Final = "home_zone"

# Vehicle
CONF_CAPACITY_KWH: Final = "capacity_kwh"
CONF_CAPACITY_ENTITY: Final = "capacity_entity"
CONF_SOC_ENTITY: Final = "soc_entity"
CONF_RANGE_ENTITY: Final = "range_entity"
CONF_CONSUMPTION: Final = "consumption_kwh_per_100km"
CONF_SOC_LIMIT_ENTITY: Final = "soc_limit_entity"

# Planning
CONF_DEPARTURE_BUFFER: Final = "departure_buffer_min"
CONF_RESERVE_PERCENT: Final = "reserve_percent"
CONF_SOC_STEP: Final = "soc_step"
CONF_LOOK_AHEAD_DAYS: Final = "look_ahead_days"
CONF_UPDATE_INTERVAL: Final = "update_interval_min"
CONF_NOTIFY: Final = "notify_target"

# Target
CONF_TARGET_TYPE: Final = "target_type"
CONF_TARGET_SOC_ENTITY: Final = "target_soc_entity"
CONF_DEPARTURE_ENTITY: Final = "departure_entity"
CONF_SET_ACTION: Final = "set_action"
CONF_CLEAR_ACTION: Final = "clear_action"

DEFAULT_HOME_ZONE: Final = "zone.home"
DEFAULT_WAZE_REGION: Final = "eu"
DEFAULT_CAPACITY_KWH: Final = 50.0
DEFAULT_CONSUMPTION: Final = 18.0
DEFAULT_DEPARTURE_BUFFER: Final = 15
DEFAULT_RESERVE_PERCENT: Final = 20
DEFAULT_SOC_STEP: Final = 1
DEFAULT_LOOK_AHEAD_DAYS: Final = 7
DEFAULT_UPDATE_INTERVAL: Final = 15

ROUTE_CACHE_TTL_MIN: Final = 60
ROUTE_FAILURE_TTL_MIN: Final = 30

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


class RoutingProvider(StrEnum):
    """Supported travel time integrations."""

    GOOGLE = "google"
    WAZE = "waze"


class PlanStatus(StrEnum):
    """State of the planner, exposed by the status sensor."""

    PLANNED = "planned"
    NO_TRIP = "no_trip"
    DEPARTURE_PASSED = "departure_passed"
    ROUTING_FAILED = "routing_failed"
    VEHICLE_DATA_MISSING = "vehicle_data_missing"
    TARGET_FAILED = "target_failed"
