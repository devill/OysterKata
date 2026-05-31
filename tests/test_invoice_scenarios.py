"""Constrained approval test for the invoice data-in seam.

One YAML scenario file per case (in tests/scenarios) lists only the inputs that
differ from the defaults below; everything omitted falls back to a sensible
default so each file stays small and the behaviour under test is obvious. The
rendered HTML invoice is the approved artefact, one .approved.html per scenario,
reviewed as a diff.

Built as the four standard approval-test parts:
- a parametrised test, scenario name as its id;
- a provider that loads every YAML file and builds the plain inputs;
- a namer mapping each scenario to its approved/received HTML;
- a reporter that is quiet in CI and opens a diff tool locally.

The test is a thin wrapper around production code: it prices and renders through
`render_invoice_html` using the deterministic fare/zone/calendar rules as-is, and
never instantiates an external service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from approvaltests import Options, verify
from approvaltests.core.reporter import Reporter
from approvaltests.namer.default_namer_factory import is_ci
from approvaltests.namer.namer_base import NamerBase
from approvaltests.reporters.diff_reporter import DiffReporter
from approvaltests.reporters.report_quietly import ReportQuietly

from oyster.generator import render_invoice_html
from oyster.model import BillingPeriod, Customer, Mode, Programme, Trip
from oyster.rules.bank_holidays import BankHolidayService
from oyster.rules.fare_table import FareTable
from oyster.rules.station_registry import StationRegistry

_TESTS_DIR = Path(__file__).resolve().parent
_SCENARIOS_DIR = _TESTS_DIR / "scenarios"
_APPROVED_DIR = _TESTS_DIR / "approved"

# --- Defaults the provider supplies for anything a scenario omits --------------

_DEFAULT_CUSTOMER_ID = "OY-7700"
_DEFAULT_CUSTOMER_NAME = "Sample Customer"
_DEFAULT_HOME_ZONE = 2
_DEFAULT_PERIOD = BillingPeriod(2026, 4)


# --- Provider: YAML files -> plain production inputs ---------------------------


@dataclass(frozen=True)
class Scenario:
    name: str
    customer: Customer
    period: BillingPeriod
    trips: list[Trip]


def load_scenarios() -> list[Scenario]:
    return [_build_scenario(path) for path in sorted(_SCENARIOS_DIR.glob("*.yaml"))]


def _build_scenario(path: Path) -> Scenario:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Scenario(
        name=path.stem,
        customer=_build_customer(raw),
        period=_build_period(raw.get("period")),
        trips=[_build_trip(trip) for trip in raw.get("trips", [])],
    )


def _build_customer(raw: dict) -> Customer:
    band = raw.get("commuter_club_band")
    return Customer(
        id=_DEFAULT_CUSTOMER_ID,
        name=_DEFAULT_CUSTOMER_NAME,
        home_zone=raw.get("home_zone", _DEFAULT_HOME_ZONE),
        enrolled=tuple(Programme(name) for name in raw.get("enrolled", [])),
        commuter_club_band=tuple(band) if band is not None else None,
        commuter_club_fee=raw.get("commuter_club_fee"),
    )


def _build_period(raw: str | None) -> BillingPeriod:
    if raw is None:
        return _DEFAULT_PERIOD
    year, month = (int(part) for part in str(raw).split("-"))
    return BillingPeriod(year, month)


def _build_trip(raw: dict) -> Trip:
    return Trip(
        touch_in=datetime.fromisoformat(raw["time"]),
        mode=Mode(raw["mode"]),
        from_station=raw.get("from"),
        to_station=raw.get("to"),
    )


# --- Namer: one scenario -> its approved/received HTML pair --------------------


class _ScenarioNamer(NamerBase):
    def __init__(self, scenario_name: str) -> None:
        super().__init__(extension=".html")
        self._scenario_name = scenario_name

    def get_file_name(self) -> str:
        return self._scenario_name

    def get_directory(self) -> str:
        return str(_APPROVED_DIR)

    def config_directory(self) -> str:
        return str(_APPROVED_DIR)


# --- Reporter: quiet in CI, opens a diff tool locally --------------------------


def _diff_reporter() -> Reporter:
    return ReportQuietly() if is_ci() else DiffReporter()


# --- The parametrised test -----------------------------------------------------


@pytest.mark.parametrize(
    "scenario", load_scenarios(), ids=lambda scenario: scenario.name
)
def test_invoice_scenario(scenario: Scenario) -> None:
    html = render_invoice_html(
        scenario.customer,
        scenario.period,
        scenario.trips,
        stations=StationRegistry(),
        fares=FareTable(),
        holidays=BankHolidayService(),
    )
    verify(
        html,
        options=Options()
        .for_file.with_extension(".html")
        .with_namer(_ScenarioNamer(scenario.name))
        .with_reporter(_diff_reporter()),
    )
