"""DEMO ONLY — generates each sample customer's HTML invoice from the simulated
external services; output varies on every run because that data is
non-deterministic. This is NOT a validation gate; do not use it to check behaviour.

Run from the repo root:  python scripts/generate_all.py

For each of the four sample customers and April 2026, generate the HTML via
`generate_invoice_html` and write it to out/<id>_2026-04.html.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oyster.generator import generate_invoice_html  # noqa: E402
from oyster.model import BillingPeriod  # noqa: E402
from oyster.rules.bank_holidays import BankHolidayService  # noqa: E402
from oyster.rules.fare_table import FareTable  # noqa: E402
from oyster.rules.station_registry import StationRegistry  # noqa: E402
from oyster.services.customer_directory import CustomerDirectory  # noqa: E402
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


def main() -> None:
    services = _services()

    for customer_id in _CUSTOMER_IDS:
        html = generate_invoice_html(customer_id, _PERIOD, **services)
        out_path = _OUT_DIR / f"{customer_id}_{_PERIOD_TEXT}.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(out_path)


if __name__ == "__main__":
    main()
