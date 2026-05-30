from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class Mode(Enum):
    BUS = "bus"
    TRAM = "tram"
    TUBE = "tube"
    OVERGROUND = "overground"
    DLR = "dlr"
    ELIZABETH = "elizabeth"
    RAIL = "rail"

    @property
    def is_rail_type(self) -> bool:
        return self not in (Mode.BUS, Mode.TRAM)


class Programme(Enum):
    RAILCARD = "railcard"
    ZONE_RESIDENT = "zone_resident"
    COMMUTER_CLUB = "commuter_club"
    GREEN_TRAVELLER = "green_traveller"


@dataclass(frozen=True)
class Trip:
    touch_in: datetime
    mode: Mode
    from_station: str
    to_station: str | None


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    home_zone: int
    enrolled: tuple[Programme, ...]
    commuter_club_band: tuple[int, int] | None
    commuter_club_fee: float | None


_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


@dataclass(frozen=True)
class BillingPeriod:
    year: int
    month: int

    def contains(self, d: date) -> bool:
        return d.year == self.year and d.month == self.month

    @property
    def label(self) -> str:
        return f"{_MONTH_NAMES[self.month - 1]} {self.year}"
