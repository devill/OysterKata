"""Simulated external system — returns non-deterministic results; never use in tests or for validation."""

from __future__ import annotations

import calendar
import random
from datetime import datetime

from oyster.model import BillingPeriod, Mode, Trip

_STATION_POOL: tuple[str, ...] = (
    "Oxford Circus",
    "King's Cross",
    "Waterloo",
    "Victoria",
    "Camden Town",
    "Stratford",
    "Ealing Broadway",
    "Lewisham",
    "Hounslow Central",
    "Harrow-on-the-Hill",
    "Cockfosters",
    "Hayes & Harlington",
    "Uxbridge",
)


class TripService:
    """Simulated external system — returns non-deterministic results; never use in tests or for validation."""

    def __init__(self) -> None:
        self._rng = random.Random()
        self._cache: dict[tuple[str, BillingPeriod], list[Trip]] = {}

    def trips_for(self, customer_id: str, period: BillingPeriod) -> list[Trip]:
        key = (customer_id, period)
        if key not in self._cache:
            self._cache[key] = self._generate(period)
        return self._cache[key]

    def _generate(self, period: BillingPeriod) -> list[Trip]:
        trips = [self._random_trip(period) for _ in range(self._rng.randint(3, 18))]
        return sorted(trips, key=lambda trip: trip.touch_in)

    def _random_trip(self, period: BillingPeriod) -> Trip:
        mode = self._rng.choice(list(Mode))
        touch_in = self._random_datetime(period)
        if mode.is_rail_type:
            from_station, to_station = self._rng.sample(_STATION_POOL, 2)
        else:
            from_station, to_station = self._rng.choice(_STATION_POOL), None
        return Trip(touch_in, mode, from_station, to_station)

    def _random_datetime(self, period: BillingPeriod) -> datetime:
        _, last_day = calendar.monthrange(period.year, period.month)
        return datetime(
            period.year,
            period.month,
            self._rng.randint(1, last_day),
            self._rng.randint(0, 23),
            self._rng.randint(0, 59),
        )
