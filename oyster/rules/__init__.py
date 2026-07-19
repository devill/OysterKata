"""Deterministic reference data consulted by the pricing engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from oyster.rules.bank_holidays import BankHolidayService
from oyster.rules.fare_table import FareTable
from oyster.rules.station_registry import StationRegistry


@dataclass(frozen=True)
class PricingRules:
    """The fare, zone and calendar reference data one pricing run needs."""

    stations: StationRegistry = field(default_factory=StationRegistry)
    fares: FareTable = field(default_factory=FareTable)
    bank_holidays: BankHolidayService = field(default_factory=BankHolidayService)
