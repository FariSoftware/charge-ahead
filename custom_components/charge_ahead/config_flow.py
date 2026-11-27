"""Config flow for Charge Ahead."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
    SchemaFlowMenuStep,
)
import voluptuous as vol

from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_CLEAR_ACTION,
    CONF_DEPARTURE_ENTITY,
    CONF_SET_ACTION,
    CONF_TARGET_SOC_ENTITY,
    CONF_TARGET_TYPE,
    DOMAIN,
    TargetType,
)

_TARGET_KEYS = (
    CONF_TARGET_SOC_ENTITY,
    CONF_DEPARTURE_ENTITY,
    CONF_SET_ACTION,
    CONF_CLEAR_ACTION,
)

TARGET_MENU = ["target_none", "target_entities", "target_action"]

CALENDAR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CALENDAR_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="calendar")
        ),
    }
)

USER_SCHEMA = vol.Schema({vol.Required(CONF_NAME): selector.TextSelector()}).extend(
    CALENDAR_SCHEMA.schema
)

TARGET_NONE_SCHEMA = vol.Schema({})

TARGET_ENTITIES_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TARGET_SOC_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["number", "input_number"])
        ),
        vol.Required(CONF_DEPARTURE_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["datetime", "input_datetime"])
        ),
    }
)

TARGET_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SET_ACTION): selector.ActionSelector(),
        vol.Optional(CONF_CLEAR_ACTION): selector.ActionSelector(),
    }
)


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


TARGET_STEPS = {
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
    "user": SchemaFlowFormStep(USER_SCHEMA, next_step="target"),
    **TARGET_STEPS,
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(CALENDAR_SCHEMA, next_step="target"),
    **TARGET_STEPS,
}


class ChargeAheadConfigFlow(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config flow for Charge Ahead."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW
    options_flow_reloads = True

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return the config entry title."""
        return cast(str, options[CONF_NAME])
