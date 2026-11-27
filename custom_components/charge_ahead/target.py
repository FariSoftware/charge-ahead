"""Plan targets: where a computed charging plan is written to.

The planner core does not know the target. It produces a ChargePlan and hands
it to a PlanTarget built from the config entry options.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any, Protocol

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.script import Script, async_validate_actions_config

from .const import (
    CONF_CLEAR_ACTION,
    CONF_DEPARTURE_ENTITY,
    CONF_SET_ACTION,
    CONF_TARGET_SOC_ENTITY,
    CONF_TARGET_TYPE,
    DOMAIN,
    TargetType,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChargePlan:
    """A charging plan for one trip."""

    target_soc: int
    departure: datetime
    energy_kwh: float | None = None

    def as_variables(self) -> dict[str, Any]:
        """Return the variables exposed to user-defined actions."""
        return {
            "target_soc": self.target_soc,
            "departure": self.departure.isoformat(),
            "energy_kwh": self.energy_kwh,
        }


class PlanTarget(Protocol):
    """A destination for charging plans."""

    async def async_apply(self, plan: ChargePlan, context: Context | None) -> None:
        """Write the plan to the target."""

    async def async_clear(self, context: Context | None) -> None:
        """Remove a previously written plan from the target."""


class NoTarget:
    """Target that writes nothing; the plan is only exposed as entities."""

    async def async_apply(self, plan: ChargePlan, context: Context | None) -> None:
        """Do nothing."""

    async def async_clear(self, context: Context | None) -> None:
        """Do nothing."""


class EntityTarget:
    """Target that writes SoC and departure into two entities."""

    _SOC_SERVICES = {
        "number": ("number", "set_value", "value"),
        "input_number": ("input_number", "set_value", "value"),
    }

    def __init__(
        self, hass: HomeAssistant, soc_entity_id: str, departure_entity_id: str
    ) -> None:
        """Initialize the target."""
        self._hass = hass
        self._soc_entity_id = soc_entity_id
        self._departure_entity_id = departure_entity_id

    async def async_apply(self, plan: ChargePlan, context: Context | None) -> None:
        """Write SoC and departure."""
        soc_domain = self._soc_entity_id.split(".", 1)[0]
        domain, service, field = self._SOC_SERVICES[soc_domain]
        await self._hass.services.async_call(
            domain,
            service,
            {"entity_id": self._soc_entity_id, field: plan.target_soc},
            blocking=True,
            context=context,
        )

        departure_domain = self._departure_entity_id.split(".", 1)[0]
        if departure_domain == "input_datetime":
            service_data = {
                "entity_id": self._departure_entity_id,
                "datetime": plan.departure.isoformat(),
            }
            await self._hass.services.async_call(
                "input_datetime",
                "set_datetime",
                service_data,
                blocking=True,
                context=context,
            )
        else:
            await self._hass.services.async_call(
                "datetime",
                "set_value",
                {
                    "entity_id": self._departure_entity_id,
                    "datetime": plan.departure,
                },
                blocking=True,
                context=context,
            )

    async def async_clear(self, context: Context | None) -> None:
        """Entity targets have no notion of an empty plan; leave values as is."""


class ActionTarget:
    """Target that runs user-defined action sequences."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        set_sequence: list[dict[str, Any]],
        clear_sequence: list[dict[str, Any]] | None,
    ) -> None:
        """Initialize the target."""
        self._set_script = Script(
            hass, set_sequence, f"{name} set plan", DOMAIN, logger=_LOGGER
        )
        self._clear_script = (
            Script(hass, clear_sequence, f"{name} clear plan", DOMAIN, logger=_LOGGER)
            if clear_sequence
            else None
        )

    async def async_apply(self, plan: ChargePlan, context: Context | None) -> None:
        """Run the set action with the plan as variables."""
        await self._set_script.async_run(plan.as_variables(), context=context)

    async def async_clear(self, context: Context | None) -> None:
        """Run the clear action, if configured."""
        if self._clear_script is not None:
            await self._clear_script.async_run({}, context=context)


async def async_build_target(
    hass: HomeAssistant, name: str, options: dict[str, Any]
) -> PlanTarget:
    """Build the plan target from config entry options."""
    target_type = TargetType(options.get(CONF_TARGET_TYPE, TargetType.NONE))

    if target_type is TargetType.ENTITIES:
        return EntityTarget(
            hass, options[CONF_TARGET_SOC_ENTITY], options[CONF_DEPARTURE_ENTITY]
        )

    if target_type is TargetType.ACTION:
        set_sequence = await async_validate_actions_config(
            hass, cv.SCRIPT_SCHEMA(options[CONF_SET_ACTION])
        )
        clear_sequence = None
        if options.get(CONF_CLEAR_ACTION):
            clear_sequence = await async_validate_actions_config(
                hass, cv.SCRIPT_SCHEMA(options[CONF_CLEAR_ACTION])
            )
        return ActionTarget(hass, name, set_sequence, clear_sequence)

    return NoTarget()
