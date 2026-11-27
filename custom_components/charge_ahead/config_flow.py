"""Config flow for Charge Ahead."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
    SchemaFlowMenuStep,
)
import voluptuous as vol

from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_CAPACITY_ENTITY,
    CONF_CAPACITY_KWH,
    CONF_CHARGE_POWER,
    CONF_CLEAR_ACTION,
    CONF_CONSUMPTION,
    CONF_DEPARTURE_BUFFER,
    CONF_DEPARTURE_ENTITY,
    CONF_GOOGLE_ENTRY,
    CONF_HOME_ZONE,
    CONF_LOOK_AHEAD_DAYS,
    CONF_NOTIFY,
    CONF_RANGE_ENTITY,
    CONF_RESERVE_PERCENT,
    CONF_ROUTING_PROVIDER,
    CONF_SET_ACTION,
    CONF_SOC_ENTITY,
    CONF_SOC_LIMIT_ENTITY,
    CONF_SOC_STEP,
    CONF_TARGET_SOC_ENTITY,
    CONF_TARGET_TYPE,
    CONF_UPDATE_INTERVAL,
    CONF_WAZE_REGION,
    DEFAULT_CAPACITY_KWH,
    DEFAULT_CHARGE_POWER,
    DEFAULT_CONSUMPTION,
    DEFAULT_DEPARTURE_BUFFER,
    DEFAULT_HOME_ZONE,
    DEFAULT_LOOK_AHEAD_DAYS,
    DEFAULT_RESERVE_PERCENT,
    DEFAULT_SOC_STEP,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_WAZE_REGION,
    DOMAIN,
    RoutingProvider,
    TargetType,
)

_TARGET_KEYS = (
    CONF_TARGET_SOC_ENTITY,
    CONF_DEPARTURE_ENTITY,
    CONF_SET_ACTION,
    CONF_CLEAR_ACTION,
)

TARGET_MENU = ["target_none", "target_entities", "target_action"]


def _number(
    minimum: float, maximum: float, step: float = 1, unit: str | None = None
) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _entity(*domains: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=list(domains)))


CALENDAR_SCHEMA = vol.Schema({vol.Required(CONF_CALENDAR_ENTITY): _entity("calendar")})

USER_SCHEMA = vol.Schema({vol.Required(CONF_NAME): selector.TextSelector()}).extend(
    CALENDAR_SCHEMA.schema
)

ROUTING_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_ROUTING_PROVIDER, default=RoutingProvider.GOOGLE.value
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[provider.value for provider in RoutingProvider],
                translation_key=CONF_ROUTING_PROVIDER,
            )
        ),
        vol.Optional(CONF_GOOGLE_ENTRY): selector.ConfigEntrySelector(
            selector.ConfigEntrySelectorConfig(integration="google_travel_time")
        ),
        vol.Required(CONF_WAZE_REGION, default=DEFAULT_WAZE_REGION): (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["eu", "us", "na", "il", "au"],
                    translation_key=CONF_WAZE_REGION,
                )
            )
        ),
        vol.Required(CONF_HOME_ZONE, default=DEFAULT_HOME_ZONE): _entity("zone"),
    }
)

VEHICLE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CAPACITY_KWH, default=DEFAULT_CAPACITY_KWH): _number(
            1, 250, 0.1, "kWh"
        ),
        vol.Optional(CONF_CAPACITY_ENTITY): _entity("sensor", "number", "input_number"),
        vol.Optional(CONF_SOC_ENTITY): _entity("sensor", "number", "input_number"),
        vol.Optional(CONF_RANGE_ENTITY): _entity("sensor", "number", "input_number"),
        vol.Required(CONF_CONSUMPTION, default=DEFAULT_CONSUMPTION): _number(
            5, 60, 0.1, "kWh/100 km"
        ),
        vol.Optional(CONF_SOC_LIMIT_ENTITY): _entity(
            "sensor", "number", "select", "input_number"
        ),
        vol.Required(CONF_CHARGE_POWER, default=DEFAULT_CHARGE_POWER): _number(
            1, 350, 0.1, "kW"
        ),
    }
)

PLANNING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEPARTURE_BUFFER, default=DEFAULT_DEPARTURE_BUFFER): _number(
            0, 240, 1, "min"
        ),
        vol.Required(CONF_RESERVE_PERCENT, default=DEFAULT_RESERVE_PERCENT): _number(
            0, 80, 1, "%"
        ),
        vol.Required(CONF_SOC_STEP, default=DEFAULT_SOC_STEP): _number(1, 10, 1, "%"),
        vol.Required(CONF_LOOK_AHEAD_DAYS, default=DEFAULT_LOOK_AHEAD_DAYS): _number(
            1, 14, 1, "d"
        ),
        vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): _number(
            5, 120, 1, "min"
        ),
        vol.Optional(CONF_NOTIFY): selector.TextSelector(),
    }
)

TARGET_NONE_SCHEMA = vol.Schema({})

TARGET_ENTITIES_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TARGET_SOC_ENTITY): _entity("number", "input_number"),
        vol.Required(CONF_DEPARTURE_ENTITY): _entity("datetime", "input_datetime"),
    }
)

TARGET_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SET_ACTION): selector.ActionSelector(),
        vol.Optional(CONF_CLEAR_ACTION): selector.ActionSelector(),
    }
)


async def _validate_routing(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    if user_input[
        CONF_ROUTING_PROVIDER
    ] == RoutingProvider.GOOGLE and not user_input.get(CONF_GOOGLE_ENTRY):
        raise SchemaFlowError("google_entry_required")
    return user_input


async def _validate_planning(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    target = (user_input.get(CONF_NOTIFY) or "").strip()
    if not target:
        user_input.pop(CONF_NOTIFY, None)
        return user_input
    hass = handler.parent_handler.hass
    domain, _, service = target.partition(".")
    is_entity = domain == "notify" and hass.states.get(target) is not None
    if not is_entity and not hass.services.has_service(domain, service):
        raise SchemaFlowError("notify_not_found")
    user_input[CONF_NOTIFY] = target
    return user_input


def _target_validator(target_type: TargetType):
    """Return a validator that records the target type and drops stale keys."""

    async def _validate(
        handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        for key in _TARGET_KEYS:
            if key not in user_input:
                handler.options.pop(key, None)
        return {**user_input, CONF_TARGET_TYPE: target_type.value}

    return _validate


COMMON_STEPS = {
    "routing": SchemaFlowFormStep(
        ROUTING_SCHEMA, validate_user_input=_validate_routing, next_step="vehicle"
    ),
    "vehicle": SchemaFlowFormStep(VEHICLE_SCHEMA, next_step="planning"),
    "planning": SchemaFlowFormStep(
        PLANNING_SCHEMA, validate_user_input=_validate_planning, next_step="target"
    ),
    "target": SchemaFlowMenuStep(TARGET_MENU),
    "target_none": SchemaFlowFormStep(
        TARGET_NONE_SCHEMA, validate_user_input=_target_validator(TargetType.NONE)
    ),
    "target_entities": SchemaFlowFormStep(
        TARGET_ENTITIES_SCHEMA,
        validate_user_input=_target_validator(TargetType.ENTITIES),
    ),
    "target_action": SchemaFlowFormStep(
        TARGET_ACTION_SCHEMA, validate_user_input=_target_validator(TargetType.ACTION)
    ),
}

CONFIG_FLOW = {
    "user": SchemaFlowFormStep(USER_SCHEMA, next_step="routing"),
    **COMMON_STEPS,
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(CALENDAR_SCHEMA, next_step="routing"),
    **COMMON_STEPS,
}


class ChargeAheadConfigFlow(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config flow for Charge Ahead."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW
    options_flow_reloads = True

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return the config entry title."""
        return cast(str, options[CONF_NAME])
