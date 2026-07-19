"""Command-line entry point: generate an HTML invoice for one customer.

Usage:
    python -m oyster.cli <customer_id> <YYYY-MM>

Example:
    python -m oyster.cli alice 2026-04
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from oyster.generator import render_invoice_html
from oyster.model import BillingPeriod
from oyster.rules.bank_holidays import BankHolidayService
from oyster.rules.fare_table import FareTable
from oyster.rules.station_registry import StationRegistry
from oyster.services.customer_directory import CustomerDirectory
from oyster.services.trip_service import TripService

_USAGE = "usage: python -m oyster.cli <customer_id> <YYYY-MM>"
_OUT_DIR = Path("out")


def _parse_period(text: str) -> BillingPeriod:
    if not re.fullmatch(r"\d{4}-\d{2}", text):
        raise ValueError(f"bad period {text!r}: expected YYYY-MM (e.g. 2026-04)")
    year, month = int(text[:4]), int(text[5:])
    if not 1 <= month <= 12:
        raise ValueError(f"bad period {text!r}: month must be 01-12")
    return BillingPeriod(year, month)


def main(argv: list[str]) -> int:
    if len(argv) == 1 and argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0
    if len(argv) != 2:
        print(_USAGE, file=sys.stderr)
        return 2

    customer_id, period_text = argv
    try:
        period = _parse_period(period_text)
        customer = CustomerDirectory().get(customer_id)
    except (ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    trips = TripService().trips_for(customer_id, period)
    html = render_invoice_html(
        customer,
        period,
        trips,
        stations=StationRegistry(),
        fares=FareTable(),
        holidays=BankHolidayService(),
    )

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUT_DIR / f"{customer_id}_{period_text}.html"
    out_path.write_text(html, encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
