"""User notifications.

The target is either a notify entity (notify.send_message) or a legacy notify
action such as notify.mobile_app_iphone. Messages are user-facing text, so they
follow the Home Assistant language (German or English).
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

TITLE = "Charge Ahead"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "above_limit": (
            "{summary} ({start}) needs {soc} %, but the charge limit "
            "({limit_source}) is {limit} %. Raise the limit in the charge "
            "controller or in the car."
        ),
        "exceeds_capacity": (
            "{summary} ({start}) needs {energy} kWh plus reserve, more than a "
            "full battery. Plan a charging stop."
        ),
        "departure_passed": (
            "Departure for {summary} would have been at {departure}. No charging "
            "plan set."
        ),
        "routing_failed": (
            "Location of {summary} ({start}) not found: {location}. No charging "
            "plan set."
        ),
        "vehicle_data_missing": (
            "Vehicle data for {summary} ({start}) is missing (battery capacity "
            "or consumption). No charging plan set."
        ),
        "target_failed": "Charging plan for {summary} could not be written: {error}",
    },
    "de": {
        "above_limit": (
            "„{summary}“ ({start}) braucht {soc} %, das Ladelimit "
            "({limit_source}) liegt bei {limit} %. Limit in der Ladesteuerung "
            "oder im Auto anheben."
        ),
        "exceeds_capacity": (
            "„{summary}“ ({start}) braucht {energy} kWh plus Reserve, mehr als "
            "ein voller Akku. Einen Ladestopp einplanen."
        ),
        "departure_passed": (
            "Die Abfahrt für „{summary}“ wäre um {departure} gewesen. Kein "
            "Ladeplan gesetzt."
        ),
        "routing_failed": (
            "Ort von „{summary}“ ({start}) nicht gefunden: {location}. Kein "
            "Ladeplan gesetzt."
        ),
        "vehicle_data_missing": (
            "Fahrzeugdaten für „{summary}“ ({start}) fehlen (Akkukapazität oder "
            "Verbrauch). Kein Ladeplan gesetzt."
        ),
        "target_failed": (
            "Ladeplan für „{summary}“ konnte nicht geschrieben werden: {error}"
        ),
    },
}


def render_message(language: str, key: str, **placeholders: object) -> str:
    """Return the message for key in the given language."""
    lang = language.split("-", 1)[0].lower()
    texts = MESSAGES.get(lang, MESSAGES["en"])
    return texts[key].format(**placeholders)


async def async_send(hass: HomeAssistant, target: str | None, message: str) -> None:
    """Send a notification; failures are logged, never raised."""
    if not target:
        _LOGGER.info("%s", message)
        return
    try:
        if hass.states.get(target) is not None:
            await hass.services.async_call(
                "notify",
                "send_message",
                {"entity_id": target, "title": TITLE, "message": message},
                blocking=True,
            )
            return
        domain, _, service = target.partition(".")
        await hass.services.async_call(
            domain,
            service,
            {"title": TITLE, "message": message},
            blocking=True,
        )
    except (HomeAssistantError, ValueError) as err:
        _LOGGER.warning("Notification via %s failed: %s", target, err)
