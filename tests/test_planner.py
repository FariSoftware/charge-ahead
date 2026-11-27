"""Tests for the planner core."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.charge_ahead.planner import (
    Leg,
    PlannerSettings,
    PlanWarning,
    Route,
    Trip,
    Vehicle,
    consumption_from_range,
    is_trip,
    next_trip,
    plan_chain,
    plan_trip,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
ELROQ = Vehicle(capacity_kwh=56, consumption_kwh_per_100km=15.5, soc_limit=80)


def _trip(hours: float, location: str | None = "Stuttgart", **kwargs) -> Trip:
    return Trip(start=NOW + timedelta(hours=hours), location=location, **kwargs)


class TestTripSelection:
    def test_all_day_event_is_no_trip(self) -> None:
        assert not is_trip(_trip(5, all_day=True))

    @pytest.mark.parametrize("location", [None, "", "   "])
    def test_event_without_location_is_no_trip(self, location) -> None:
        assert not is_trip(_trip(5, location=location))

    @pytest.mark.parametrize(
        "location", ["Online", "teams", "https://zoom.us/j/123", "msteams://x"]
    )
    def test_online_event_is_no_trip(self, location) -> None:
        assert not is_trip(_trip(5, location=location))

    def test_next_trip_picks_earliest_future_trip(self) -> None:
        events = [
            _trip(-1),
            _trip(8, summary="later"),
            _trip(3, summary="next"),
            _trip(2, location=None),
            _trip(1, all_day=True),
        ]
        assert next_trip(events, NOW).summary == "next"

    def test_next_trip_none(self) -> None:
        assert next_trip([_trip(-2), _trip(4, location=None)], NOW) is None


class TestPlanTrip:
    def test_departure_subtracts_travel_time_and_buffer(self) -> None:
        trip = _trip(5)
        route = Route(distance_km=30, duration=timedelta(minutes=40))
        settings = PlannerSettings(departure_buffer=timedelta(minutes=10))

        plan = plan_trip(trip, route, ELROQ, settings, NOW)

        assert plan.departure == trip.start - timedelta(minutes=50)
        assert plan.warnings == frozenset()

    def test_soc_covers_round_trip_plus_reserve(self) -> None:
        # 2 x 100 km x 15.5 kWh/100 km = 31 kWh = 55.36 % of 56 kWh; + 20 % reserve
        route = Route(distance_km=100, duration=timedelta(hours=1))

        plan = plan_trip(_trip(5), route, ELROQ, PlannerSettings(), NOW)

        assert plan.energy_kwh == 31.0
        assert plan.target_soc == 76

    def test_soc_rounds_up_to_step(self) -> None:
        route = Route(distance_km=100, duration=timedelta(hours=1))
        settings = PlannerSettings(soc_step=5)

        plan = plan_trip(_trip(5), route, ELROQ, settings, NOW)

        assert plan.target_soc == 80

    def test_exact_step_is_not_rounded_further(self) -> None:
        vehicle = Vehicle(capacity_kwh=50, consumption_kwh_per_100km=10)
        route = Route(distance_km=50, duration=timedelta(hours=1))
        settings = PlannerSettings(reserve_percent=10, soc_step=5)

        # 2 x 50 x 10 / 100 = 10 kWh = 20 %; + 10 % = 30 %
        plan = plan_trip(_trip(5), route, vehicle, settings, NOW)

        assert plan.target_soc == 30

    def test_above_limit_warns(self) -> None:
        route = Route(distance_km=120, duration=timedelta(hours=1))

        plan = plan_trip(_trip(5), route, ELROQ, PlannerSettings(), NOW)

        assert plan.target_soc > 80
        assert PlanWarning.ABOVE_LIMIT in plan.warnings

    def test_exceeds_capacity_caps_at_100(self) -> None:
        route = Route(distance_km=300, duration=timedelta(hours=3))

        plan = plan_trip(_trip(10), route, ELROQ, PlannerSettings(), NOW)

        assert plan.target_soc == 100
        assert PlanWarning.EXCEEDS_CAPACITY in plan.warnings
        assert PlanWarning.ABOVE_LIMIT in plan.warnings

    def test_departure_passed(self) -> None:
        route = Route(distance_km=30, duration=timedelta(hours=1))

        plan = plan_trip(_trip(0.5), route, ELROQ, PlannerSettings(), NOW)

        assert PlanWarning.DEPARTURE_PASSED in plan.warnings

    def test_no_limit_no_limit_warning(self) -> None:
        vehicle = Vehicle(capacity_kwh=56, consumption_kwh_per_100km=15.5)
        route = Route(distance_km=120, duration=timedelta(hours=1))

        plan = plan_trip(_trip(5), route, vehicle, PlannerSettings(), NOW)

        assert PlanWarning.ABOVE_LIMIT not in plan.warnings


class TestConsumptionFromRange:
    def test_from_elroq_values(self) -> None:
        # 56 kWh x 52 % / 188 km = 15.49 kWh/100 km
        assert consumption_from_range(56, 52, 188) == pytest.approx(15.49, abs=0.01)

    @pytest.mark.parametrize(
        ("capacity", "soc", "range_km"), [(0, 50, 100), (56, 0, 100), (56, 50, 0)]
    )
    def test_invalid_input(self, capacity, soc, range_km) -> None:
        assert consumption_from_range(capacity, soc, range_km) is None


class TestPlanChain:
    """Follow-up trips that cannot be recharged in between."""

    ELROQ_11KW = Vehicle(
        capacity_kwh=56, consumption_kwh_per_100km=15.5, charge_power_kw=11
    )

    def _legs(self, gap: timedelta) -> list[Leg]:
        # Leg 1: 100 km, 1 h each way, event 5 h from now lasting 1 h,
        # back home at +7 h. Leg 2: 50 km, 1 h each way, departure after gap.
        first = Leg(
            Trip(
                start=NOW + timedelta(hours=5),
                end=NOW + timedelta(hours=6),
                location="A",
            ),
            Route(distance_km=100, duration=timedelta(hours=1)),
        )
        second_start = NOW + timedelta(hours=7) + gap + timedelta(minutes=75)
        second = Leg(
            Trip(start=second_start, location="B"),
            Route(distance_km=50, duration=timedelta(hours=1)),
        )
        return [first, second]

    def test_short_gap_raises_first_target(self) -> None:
        # Reserve 11.2 kWh. Leg 2 needs 15.5 + 11.2 = 26.7 kWh at departure;
        # 1 h at 11 kW recharges 11 kWh, so 15.7 kWh must be left after leg 1.
        # Leg 1: 31 + 15.7 = 46.7 kWh = 83.4 % -> 84 %.
        plan = plan_chain(
            self._legs(timedelta(hours=1)), self.ELROQ_11KW, PlannerSettings(), NOW
        )

        assert plan.target_soc == 84
        assert plan.energy_kwh == 35.5
        assert plan.chained_trips == 1
        assert plan.trip.location == "A"

    def test_long_gap_plans_first_trip_alone(self) -> None:
        plan = plan_chain(
            self._legs(timedelta(hours=6)), self.ELROQ_11KW, PlannerSettings(), NOW
        )

        assert plan.target_soc == 76
        assert plan.chained_trips == 0

    def test_unknown_charge_power_ignores_follow_up(self) -> None:
        plan = plan_chain(self._legs(timedelta(hours=1)), ELROQ, PlannerSettings(), NOW)

        assert plan.target_soc == 76
        assert plan.chained_trips == 0
