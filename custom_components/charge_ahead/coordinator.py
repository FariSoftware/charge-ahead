"""Coordinator: reads the calendar, routes, plans and writes the plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import ATTR_FRIENDLY_NAME, CONF_NAME
from homeassistant.core import (
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_CAPACITY_ENTITY,
    CONF_CAPACITY_KWH,
    CONF_CONSUMPTION,
    CONF_DEPARTURE_BUFFER,
    CONF_GOOGLE_ENTRY,
    CONF_HOME_ZONE,
    CONF_LOOK_AHEAD_DAYS,
    CONF_NOTIFY,
    CONF_RANGE_ENTITY,
    CONF_RESERVE_PERCENT,
    CONF_ROUTING_PROVIDER,
    CONF_SOC_ENTITY,
    CONF_SOC_LIMIT_ENTITY,
    CONF_SOC_STEP,
    CONF_UPDATE_INTERVAL,
    CONF_WAZE_REGION,
    DEFAULT_CAPACITY_KWH,
    DEFAULT_CONSUMPTION,
    DEFAULT_DEPARTURE_BUFFER,
    DEFAULT_HOME_ZONE,
    DEFAULT_LOOK_AHEAD_DAYS,
    DEFAULT_RESERVE_PERCENT,
    DEFAULT_SOC_STEP,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_WAZE_REGION,
    DOMAIN,
    ROUTE_CACHE_TTL_MIN,
    ROUTE_FAILURE_TTL_MIN,
    PlanStatus,
    RoutingProvider,
)
from .notifications import async_send, render_message
from .planner import (
    PlannerSettings,
    PlanWarning,
    Route,
    Trip,
    TripPlan,
    Vehicle,
    consumption_from_range,
    next_trip,
    plan_trip,
)
from .routing import RoutingError, async_route_location
from .target import ChargePlan, PlanTarget

if TYPE_CHECKING:
    from . import ChargeAheadConfigEntry

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


@dataclass(slots=True)
class ChargeAheadData:
    """Result of one planning run."""

    status: PlanStatus
    trip: Trip | None = None
    route: Route | None = None
    plan: TripPlan | None = None
    consumption_kwh_per_100km: float | None = None
    warnings: frozenset[PlanWarning] = field(default_factory=frozenset)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _AppliedPlan:
    target_soc: int
    departure: datetime


def parse_event(event: dict[str, Any]) -> Trip | None:
    """Turn a calendar.get_events entry into a Trip."""
    raw_start = event.get("start")
    if not raw_start:
        return None
    if "T" not in raw_start and " " not in raw_start.strip():
        parsed_date = dt_util.parse_date(raw_start)
        if parsed_date is None:
            return None
        return Trip(
            start=dt_util.start_of_local_day(parsed_date),
            location=event.get("location"),
            summary=event.get("summary", ""),
            all_day=True,
        )
    start = dt_util.parse_datetime(raw_start)
    if start is None:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt_util.get_default_time_zone())
    return Trip(
        start=start,
        location=event.get("location"),
        summary=event.get("summary", ""),
    )


def _float_state(hass: HomeAssistant, entity_id: str | None) -> float | None:
    if not entity_id or (state := hass.states.get(entity_id)) is None:
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


class ChargeAheadCoordinator(DataUpdateCoordinator[ChargeAheadData]):
    """Plans charging for the next calendar trip."""

    config_entry: ChargeAheadConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ChargeAheadConfigEntry,
        target: PlanTarget,
    ) -> None:
        """Initialize the coordinator."""
        self.options: dict[str, Any] = dict(entry.options)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(
                minutes=self.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ),
        )
        self.target = target
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._applied: _AppliedPlan | None = None
        self._route_cache: dict[str, tuple[datetime, Route | None]] = {}
        self._notified: set[tuple[str, str]] = set()

    async def async_load(self) -> None:
        """Restore the last plan written to the target.

        Without this, a plan written before a restart or reload would never be
        cleared if its trip disappears (for example after switching calendars).
        """
        stored = await self._store.async_load()
        if not stored:
            return
        departure = dt_util.parse_datetime(stored.get("departure", ""))
        if departure is not None:
            self._applied = _AppliedPlan(int(stored["target_soc"]), departure)

    async def async_reapply(self) -> None:
        """Plan again and write the result even if it did not change."""
        self._applied = None
        await self.async_refresh()

    async def _async_set_applied(self, applied: _AppliedPlan | None) -> None:
        self._applied = applied
        if applied is None:
            await self._store.async_remove()
            return
        await self._store.async_save(
            {
                "target_soc": applied.target_soc,
                "departure": applied.departure.isoformat(),
            }
        )

    @callback
    def async_track_calendar(self) -> None:
        """Refresh when the calendar entity changes."""

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        self.config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self.options[CONF_CALENDAR_ENTITY], _changed
            )
        )

    @property
    def settings(self) -> PlannerSettings:
        """Planner settings from the options."""
        return PlannerSettings(
            departure_buffer=timedelta(
                minutes=self.options.get(
                    CONF_DEPARTURE_BUFFER, DEFAULT_DEPARTURE_BUFFER
                )
            ),
            reserve_percent=int(
                self.options.get(CONF_RESERVE_PERCENT, DEFAULT_RESERVE_PERCENT)
            ),
            soc_step=int(self.options.get(CONF_SOC_STEP, DEFAULT_SOC_STEP)),
        )

    async def _async_update_data(self) -> ChargeAheadData:
        now = dt_util.now()
        trip = next_trip(await self._async_fetch_trips(now), now)

        if trip is None:
            await self._async_clear(now)
            return ChargeAheadData(status=PlanStatus.NO_TRIP)

        self._forget_other_trips(trip)
        location = trip.location or ""

        try:
            route = await self._async_route(location, now)
        except RoutingError as err:
            await self._async_notify_once(
                trip, "routing_failed", location=location.replace("\n", ", ")
            )
            return ChargeAheadData(
                status=PlanStatus.ROUTING_FAILED, trip=trip, error=str(err)
            )

        vehicle, consumption = self._vehicle()
        if vehicle is None:
            await self._async_notify_once(trip, "vehicle_data_missing")
            return ChargeAheadData(
                status=PlanStatus.VEHICLE_DATA_MISSING, trip=trip, route=route
            )

        plan = plan_trip(trip, route, vehicle, self.settings, now)
        data = ChargeAheadData(
            status=PlanStatus.PLANNED,
            trip=trip,
            route=route,
            plan=plan,
            consumption_kwh_per_100km=round(consumption, 2),
            warnings=plan.warnings,
        )

        await self._async_notify_warnings(plan, vehicle)

        if PlanWarning.DEPARTURE_PASSED in plan.warnings:
            data.status = PlanStatus.DEPARTURE_PASSED
            return data

        try:
            await self._async_apply(plan)
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.error("Writing the plan to the target failed: %s", err)
            await self._async_notify_once(trip, "target_failed", error=str(err))
            data.status = PlanStatus.TARGET_FAILED
            data.error = str(err)
        return data

    async def _async_fetch_trips(self, now: datetime) -> list[Trip]:
        calendar = self.options[CONF_CALENDAR_ENTITY]
        days = self.options.get(CONF_LOOK_AHEAD_DAYS, DEFAULT_LOOK_AHEAD_DAYS)
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": calendar,
                    "start_date_time": now.isoformat(),
                    "end_date_time": (now + timedelta(days=days)).isoformat(),
                },
                blocking=True,
                return_response=True,
            )
        except (HomeAssistantError, ValueError) as err:
            raise UpdateFailed(f"Reading {calendar} failed: {err}") from err
        events = (response or {}).get(calendar, {}).get("events", [])
        return [trip for event in events if (trip := parse_event(event))]

    def _origin(self) -> str:
        zone_id = self.options.get(CONF_HOME_ZONE, DEFAULT_HOME_ZONE)
        if (zone := self.hass.states.get(zone_id)) is not None:
            lat = zone.attributes.get("latitude")
            lon = zone.attributes.get("longitude")
            if lat is not None and lon is not None:
                return f"{lat},{lon}"
        return f"{self.hass.config.latitude},{self.hass.config.longitude}"

    async def _async_route(self, location: str, now: datetime) -> Route:
        cached = self._route_cache.get(location)
        if cached is not None:
            fetched, route = cached
            ttl = ROUTE_CACHE_TTL_MIN if route else ROUTE_FAILURE_TTL_MIN
            if now - fetched < timedelta(minutes=ttl):
                if route is None:
                    raise RoutingError("location not found (cached)")
                return route
        try:
            route = await async_route_location(
                self.hass,
                RoutingProvider(
                    self.options.get(CONF_ROUTING_PROVIDER, RoutingProvider.GOOGLE)
                ),
                self._origin(),
                location,
                google_entry_id=self._google_entry_id(),
                waze_region=self.options.get(CONF_WAZE_REGION, DEFAULT_WAZE_REGION),
            )
        except RoutingError:
            self._route_cache[location] = (now, None)
            raise
        self._route_cache[location] = (now, route)
        return route

    def _google_entry_id(self) -> str | None:
        if entry_id := self.options.get(CONF_GOOGLE_ENTRY):
            return entry_id
        entries = self.hass.config_entries.async_loaded_entries("google_travel_time")
        return entries[0].entry_id if entries else None

    def _vehicle(self) -> tuple[Vehicle | None, float]:
        capacity = _float_state(self.hass, self.options.get(CONF_CAPACITY_ENTITY))
        if capacity is None:
            capacity = float(self.options.get(CONF_CAPACITY_KWH, DEFAULT_CAPACITY_KWH))

        consumption = None
        soc = _float_state(self.hass, self.options.get(CONF_SOC_ENTITY))
        range_km = _float_state(self.hass, self.options.get(CONF_RANGE_ENTITY))
        if soc is not None and range_km is not None:
            consumption = consumption_from_range(capacity, soc, range_km)
        if consumption is None:
            consumption = float(self.options.get(CONF_CONSUMPTION, DEFAULT_CONSUMPTION))

        if capacity <= 0 or consumption <= 0:
            return None, consumption

        limit = _float_state(self.hass, self.options.get(CONF_SOC_LIMIT_ENTITY))
        return (
            Vehicle(
                capacity_kwh=capacity,
                consumption_kwh_per_100km=consumption,
                soc_limit=int(limit) if limit is not None else None,
            ),
            consumption,
        )

    async def _async_apply(self, plan: TripPlan) -> None:
        applied = _AppliedPlan(plan.target_soc, plan.departure)
        if applied == self._applied:
            return
        await self.target.async_apply(
            ChargePlan(
                target_soc=plan.target_soc,
                departure=plan.departure,
                energy_kwh=plan.energy_kwh,
            ),
            Context(),
        )
        await self._async_set_applied(applied)

    async def _async_clear(self, now: datetime) -> None:
        """Clear a written plan whose trip is gone before its departure."""
        if self._applied is None:
            return
        if self._applied.departure > now:
            try:
                await self.target.async_clear(Context())
            except (HomeAssistantError, vol.Invalid) as err:
                _LOGGER.error("Clearing the plan on the target failed: %s", err)
                return
        await self._async_set_applied(None)

    def _forget_other_trips(self, trip: Trip) -> None:
        key = self._trip_key(trip)
        self._notified = {item for item in self._notified if item[0] == key}

    @staticmethod
    def _trip_key(trip: Trip) -> str:
        return f"{trip.start.isoformat()}|{trip.location}"

    def _format_time(self, value: datetime | date) -> str:
        if isinstance(value, datetime):
            return dt_util.as_local(value).strftime("%d.%m. %H:%M")
        return value.strftime("%d.%m.")

    async def _async_notify_warnings(self, plan: TripPlan, vehicle: Vehicle) -> None:
        for warning in sorted(plan.warnings):
            extra: dict[str, Any] = {}
            if warning is PlanWarning.ABOVE_LIMIT:
                limit_entity = self.options.get(CONF_SOC_LIMIT_ENTITY)
                state = self.hass.states.get(limit_entity) if limit_entity else None
                extra = {
                    "limit": vehicle.soc_limit,
                    "limit_source": state.attributes.get(
                        ATTR_FRIENDLY_NAME, limit_entity
                    )
                    if state
                    else limit_entity,
                }
            await self._async_notify_once(
                plan.trip,
                warning.value,
                soc=plan.target_soc,
                energy=plan.energy_kwh,
                departure=self._format_time(plan.departure),
                **extra,
            )

    async def _async_notify_once(
        self, trip: Trip, kind: str, **placeholders: Any
    ) -> None:
        key = (self._trip_key(trip), kind)
        if key in self._notified:
            return
        self._notified.add(key)
        message = render_message(
            self.hass.config.language,
            kind,
            summary=trip.summary or self.options.get(CONF_NAME, ""),
            start=self._format_time(trip.start),
            **placeholders,
        )
        await async_send(self.hass, self.options.get(CONF_NOTIFY), message)
