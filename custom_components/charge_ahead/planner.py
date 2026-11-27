"""Planner core: from calendar trips to a charging plan.

Pure Python without Home Assistant imports, so it can be tested in isolation.
The integration feeds it calendar events, routing results and vehicle data.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
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
    end: datetime | None = None


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
    charge_power_kw: float | None = None


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
class Leg:
    """A trip together with its route."""

    trip: Trip
    route: Route

    def departure(self, settings: PlannerSettings) -> datetime:
        """Time to leave home."""
        return self.trip.start - self.route.duration - settings.departure_buffer

    def return_home(self) -> datetime:
        """Time the car is back home."""
        return (self.trip.end or self.trip.start) + self.route.duration

    def energy_kwh(self, vehicle: Vehicle, settings: PlannerSettings) -> float:
        """Energy for this trip (outbound and return)."""
        return (
            self.route.distance_km
            * settings.trip_factor
            * vehicle.consumption_kwh_per_100km
            / 100
        )


@dataclass(frozen=True, slots=True)
class TripPlan:
    """The charging plan for the next trip.

    energy_kwh is the energy needed at departure above the reserve. With
    follow-up trips that cannot be recharged in between, it includes their
    shortfall; chained_trips counts those trips.
    """

    trip: Trip
    route: Route
    departure: datetime
    energy_kwh: float
    target_soc: int
    warnings: frozenset[PlanWarning] = field(default_factory=frozenset)
    chained_trips: int = 0


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


def upcoming_trips(events: Iterable[Trip], now: datetime) -> list[Trip]:
    """Return all trips that start after now, earliest first."""
    return sorted(
        (event for event in events if is_trip(event) and event.start > now),
        key=lambda event: event.start,
    )


def next_trip(events: Iterable[Trip], now: datetime) -> Trip | None:
    """Return the earliest trip that starts after now."""
    trips = upcoming_trips(events, now)
    return trips[0] if trips else None


def recharge_kwh(gap: timedelta, vehicle: Vehicle) -> float:
    """Energy the car can recharge at home within gap."""
    if vehicle.charge_power_kw is None:
        return math.inf
    hours = max(gap.total_seconds(), 0) / 3600
    return hours * vehicle.charge_power_kw


def can_fully_recharge(gap: timedelta, vehicle: Vehicle) -> bool:
    """Return whether the time at home suffices for a full charge."""
    return recharge_kwh(gap, vehicle) >= vehicle.capacity_kwh


def consumption_from_range(
    capacity_kwh: float, soc_percent: float, range_km: float
) -> float | None:
    """Derive consumption in kWh/100 km from the car's own range estimate."""
    if capacity_kwh <= 0 or soc_percent <= 0 or range_km <= 0:
        return None
    return capacity_kwh * soc_percent / 100 / range_km * 100


def _round_up(value: float, step: int) -> int:
    return int(math.ceil(value / step - 1e-9) * step)


def plan_chain(
    legs: Sequence[Leg],
    vehicle: Vehicle,
    settings: PlannerSettings,
    now: datetime,
) -> TripPlan:
    """Plan the first leg, taking follow-up legs into account.

    Works backwards: before each leg the battery must hold the leg's energy
    plus whatever the next leg needs beyond what can be recharged at home in
    between, but never less than the reserve.
    """
    if not legs:
        raise ValueError("at least one leg is required")

    reserve_kwh = vehicle.capacity_kwh * settings.reserve_percent / 100
    required = legs[-1].energy_kwh(vehicle, settings) + reserve_kwh
    chained = 0
    for index in range(len(legs) - 2, -1, -1):
        leg, following = legs[index], legs[index + 1]
        gap = following.departure(settings) - leg.return_home()
        shortfall = required - recharge_kwh(gap, vehicle)
        if shortfall > reserve_kwh:
            chained = len(legs) - 1 - index
        required = leg.energy_kwh(vehicle, settings) + max(reserve_kwh, shortfall)

    first = legs[0]
    departure = first.departure(settings)
    target_soc = _round_up(required / vehicle.capacity_kwh * 100, settings.soc_step)

    warnings: set[PlanWarning] = set()
    if target_soc > 100:
        warnings.add(PlanWarning.EXCEEDS_CAPACITY)
        target_soc = 100
    if vehicle.soc_limit is not None and target_soc > vehicle.soc_limit:
        warnings.add(PlanWarning.ABOVE_LIMIT)
    if departure <= now:
        warnings.add(PlanWarning.DEPARTURE_PASSED)

    return TripPlan(
        trip=first.trip,
        route=first.route,
        departure=departure,
        energy_kwh=round(required - reserve_kwh, 2),
        target_soc=target_soc,
        warnings=frozenset(warnings),
        chained_trips=chained,
    )


def plan_trip(
    trip: Trip,
    route: Route,
    vehicle: Vehicle,
    settings: PlannerSettings,
    now: datetime,
) -> TripPlan:
    """Plan a single trip."""
    return plan_chain([Leg(trip, route)], vehicle, settings, now)
