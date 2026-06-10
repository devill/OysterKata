"""Provider + namer for the Oyster invoice CONSTRAINED approval test.

This is the "constrained test" variant of the approved-scenario family: the case
input lives in its own readable YAML file (tests/scenarios/<name>.yaml) and the
approved output is the rendered HTML (tests/approved/<name>.approved.html). One
executable test in test_invoice_scenarios.py flows every scenario through the
single `render_invoice_html` data-in seam.

Only NON-DEFAULT inputs need appear in a scenario file; everything omitted falls
back to the defaults below. No external service (CustomerDirectory / TripService)
is touched — scenarios are plain data parsed straight into the domain types.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from approvaltests.namer.namer_base import NamerBase

from oyster.model import BillingPeriod, Customer, Mode, Programme, Trip

_DEFAULT_ID = "test-customer"
_DEFAULT_NAME = "Test Customer"
_DEFAULT_HOME_ZONE = 1
_DEFAULT_PERIOD = BillingPeriod(2026, 4)
_TIME_FORMAT = "%Y-%m-%d %H:%M"


class ScenarioNamer(NamerBase):
    """Maps a scenario to tests/approved/<name>.approved.html and its received twin."""

    def __init__(self, name: str, approved_dir: Path):
        super().__init__(extension=".html")
        self._name = name
        self._approved_dir = approved_dir

    def get_file_name(self) -> str:
        return self._name

    def get_directory(self) -> str:
        return str(self._approved_dir)

    def config_directory(self) -> str:
        return str(self._approved_dir)


class Scenario:
    """A single parsed scenario: plain domain data, ready for the data-in seam."""

    def __init__(self, name: str, customer: Customer, period: BillingPeriod,
                 trips: list[Trip]):
        self._name = name
        self.customer = customer
        self.period = period
        self.trips = trips

    def name(self) -> str:
        return self._name


def _parse_period(raw: str | None) -> BillingPeriod:
    if raw is None:
        return _DEFAULT_PERIOD
    year, month = raw.split("-")
    return BillingPeriod(int(year), int(month))


def _parse_band(raw: list[int] | None) -> tuple[int, int] | None:
    if raw is None:
        return None
    return (raw[0], raw[1])


def _parse_trip(raw: dict) -> Trip:
    return Trip(
        touch_in=datetime.strptime(raw["at"], _TIME_FORMAT),
        mode=Mode(raw["mode"]),
        from_station=raw["from"],
        to_station=raw.get("to"),
    )


def _build_scenario(name: str, data: dict) -> Scenario:
    customer = Customer(
        id=_DEFAULT_ID,
        name=_DEFAULT_NAME,
        home_zone=data.get("home_zone", _DEFAULT_HOME_ZONE),
        enrolled=tuple(Programme(p) for p in data.get("enrolled", [])),
        commuter_club_band=_parse_band(data.get("commuter_club_band")),
        commuter_club_fee=data.get("commuter_club_fee"),
    )
    period = _parse_period(data.get("period"))
    trips = [_parse_trip(t) for t in data.get("trips", [])]
    return Scenario(name, customer, period, trips)


def scenario_provider(scenarios_dir: Path):
    for scenario_file in sorted(scenarios_dir.glob("*.yaml")):
        data = yaml.safe_load(scenario_file.read_text()) or {}
        yield _build_scenario(scenario_file.stem, data)
