"""Planner core: from calendar trips to a charging plan.

Pure Python without Home Assistant imports, so it can be tested in isolation.
The integration feeds it calendar events, routing results and vehicle data.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
import math


@dataclass(frozen=True, slots=True)
class Trip:
    """A calendar event that may be a trip."""

    start: datetime
    location: str | None
    summary: str = ""
    all_day: bool = False


@dataclass(frozen=True, slots=True)
class Route:
    """Routing result from home to the trip location."""

    distance_km: float
    duration: timedelta


@dataclass(frozen=True, slots=True)
class Vehicle:
    """Vehicle data used for the plan."""

    capacity_kwh: float
    consumption_kwh_per_100km: float
    soc_limit: int | None = None


@dataclass(frozen=True, slots=True)
class PlannerSettings:
    """User settings for the planner."""

    departure_buffer: timedelta = timedelta(minutes=15)
    reserve_percent: int = 20
    soc_step: int = 1
    trip_factor: float = 2.0


class PlanWarning(StrEnum):
    """Conditions the user should know about."""

    ABOVE_LIMIT = "above_limit"
    EXCEEDS_CAPACITY = "exceeds_capacity"
    DEPARTURE_PASSED = "departure_passed"


@dataclass(frozen=True, slots=True)
class TripPlan:
    """The charging plan for one trip."""

    trip: Trip
    route: Route
    departure: datetime
    energy_kwh: float
    target_soc: int
    warnings: frozenset[PlanWarning] = field(default_factory=frozenset)


_VIRTUAL_LOCATIONS = frozenset(
    {"online", "remote", "virtual", "zoom", "teams", "webex"}
)


def is_virtual_location(location: str) -> bool:
    """Return whether a location is an online meeting rather than a place."""
    text = location.strip().lower()
    return (
        text in _VIRTUAL_LOCATIONS
        or text.startswith(("http://", "https://"))
        or "://" in text
    )


def is_trip(event: Trip) -> bool:
    """Return whether an event counts as a trip."""
    if event.all_day or not event.location or not event.location.strip():
        return False
    return not is_virtual_location(event.location)


def next_trip(events: Iterable[Trip], now: datetime) -> Trip | None:
    """Return the earliest trip that starts after now."""
    upcoming = [event for event in events if is_trip(event) and event.start > now]
    return min(upcoming, key=lambda event: event.start, default=None)


def consumption_from_range(
    capacity_kwh: float, soc_percent: float, range_km: float
) -> float | None:
    """Derive consumption in kWh/100 km from the car's own range estimate."""
    if capacity_kwh <= 0 or soc_percent <= 0 or range_km <= 0:
        return None
    return capacity_kwh * soc_percent / 100 / range_km * 100


def _round_up(value: float, step: int) -> int:
    return int(math.ceil(value / step - 1e-9) * step)


def plan_trip(
    trip: Trip,
    route: Route,
    vehicle: Vehicle,
    settings: PlannerSettings,
    now: datetime,
) -> TripPlan:
    """Compute departure time, energy and target SoC for a trip."""
    departure = trip.start - route.duration - settings.departure_buffer

    energy_kwh = (
        route.distance_km
        * settings.trip_factor
        * vehicle.consumption_kwh_per_100km
        / 100
    )
    needed_percent = energy_kwh / vehicle.capacity_kwh * 100 + settings.reserve_percent
    target_soc = _round_up(needed_percent, settings.soc_step)

    warnings: set[PlanWarning] = set()
    if target_soc > 100:
        warnings.add(PlanWarning.EXCEEDS_CAPACITY)
        target_soc = 100
    if vehicle.soc_limit is not None and target_soc > vehicle.soc_limit:
        warnings.add(PlanWarning.ABOVE_LIMIT)
    if departure <= now:
        warnings.add(PlanWarning.DEPARTURE_PASSED)

    return TripPlan(
        trip=trip,
        route=route,
        departure=departure,
        energy_kwh=round(energy_kwh, 2),
        target_soc=target_soc,
        warnings=frozenset(warnings),
    )
