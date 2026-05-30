"""Phase 4 gate: generate every sample customer's invoice and verify it.

Run from the repo root:  python scripts/generate_all.py

For each of the four sample customers and April 2026, generate the HTML via
`generate_invoice_html`, write it to out/<id>_2026-04.html, and assert the
output is well-formed HTML carrying the customer's name, grand total, and trip
table, plus a few content-fidelity checks against the pricing engine.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oyster.generator import generate_invoice_html, invoice_to_context  # noqa: E402
from oyster.model import BillingPeriod  # noqa: E402
from oyster.pricing import Services, compute_invoice  # noqa: E402
from oyster.services.bank_holidays import BankHolidayService  # noqa: E402
from oyster.services.customer_directory import CustomerDirectory  # noqa: E402
from oyster.services.fare_table import FareTable  # noqa: E402
from oyster.services.station_registry import StationRegistry  # noqa: E402
from oyster.services.trip_service import TripService  # noqa: E402

_PERIOD = BillingPeriod(2026, 4)
_PERIOD_TEXT = "2026-04"
_CUSTOMER_IDS = ("alice", "bob", "carol", "dave")
_OUT_DIR = ROOT / "out"


def _services() -> dict:
    return {
        "customers": CustomerDirectory(),
        "trips": TripService(),
        "stations": StationRegistry(),
        "fares": FareTable(),
        "holidays": BankHolidayService(),
    }


def _assert_well_formed(html: str, customer_id: str, context: dict) -> None:
    assert html, f"{customer_id}: empty output"
    assert "<!DOCTYPE html>" in html, f"{customer_id}: missing doctype"
    assert "</html>" in html, f"{customer_id}: missing closing </html>"
    assert "Trips" in html, f"{customer_id}: missing trip table heading"
    assert context["customer_name"] in html, f"{customer_id}: customer name missing"
    assert context["grand_total"] in html, f"{customer_id}: grand total missing"


def _assert_content_fidelity(htmls: dict[str, str]) -> None:
    assert "£150.00" in htmls["dave"], "dave: commuter club fee £150.00 missing"
    assert "Commuter Club" in htmls["dave"], "dave: Commuter Club programme missing"

    assert "Green Traveller" in htmls["bob"], "bob: Green Traveller upsell missing"
    assert "Save" in htmls["bob"], "bob: upsell saving missing"

    assert "Monthly cap" in htmls["alice"], "alice: monthly cap label missing"
    assert "£40.00" in htmls["alice"], "alice: rail monthly-cap discount £40.00 missing"


def main() -> None:
    services = _services()
    htmls: dict[str, str] = {}

    for customer_id in _CUSTOMER_IDS:
        html = generate_invoice_html(customer_id, _PERIOD, **services)
        htmls[customer_id] = html

        # Re-derive the context to check name/total against the engine, not magic strings.
        engine_services = Services(
            customers=services["customers"],
            trips=services["trips"],
            stations=services["stations"],
            fares=services["fares"],
            bank_holidays=services["holidays"],
        )
        customer = services["customers"].get(customer_id)
        context = invoice_to_context(compute_invoice(customer, _PERIOD, engine_services))
        _assert_well_formed(html, customer_id, context)

        out_path = _OUT_DIR / f"{customer_id}_{_PERIOD_TEXT}.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(out_path)

    _assert_content_fidelity(htmls)
    print("generate_all OK")


if __name__ == "__main__":
    main()
