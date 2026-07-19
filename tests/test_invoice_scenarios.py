"""The ONE executable test, parametrized over every scenario file.

Each tests/scenarios/<name>.yaml flows through this single test via the data-in
seam `render_invoice_html`. The scenario filename stem is the pytest id, so a
failure points straight at the offending file. Adding a case means adding a YAML
file and approving its rendered HTML — never writing a new test method.

Only the deterministic reference data (StationRegistry, FareTable,
BankHolidayService) is used; the external services are never touched.
"""

from pathlib import Path

import pytest
from approvaltests import Options, verify

from oyster.generator import render_invoice_html
from oyster.rules import PricingRules

from scenario_support import ScenarioNamer, scenario_provider

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
APPROVED_DIR = Path(__file__).parent / "approved"


@pytest.mark.parametrize(
    "scenario",
    list(scenario_provider(SCENARIOS_DIR)),
    ids=lambda scenario: scenario.name(),
)
def test_invoice_matches_approved(scenario):
    html = render_invoice_html(
        scenario.customer,
        scenario.period,
        scenario.trips,
        rules=PricingRules(),
    )
    options = (
        Options()
        .for_file.with_extension(".html")
        .with_namer(ScenarioNamer(scenario.name(), APPROVED_DIR))
    )
    verify(html, options=options)
