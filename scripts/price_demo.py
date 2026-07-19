"""DEMO ONLY — prices all four sample customers for April 2026 and prints a
per-customer summary from the simulated external services; output varies on
every run because that data is non-deterministic. This is NOT a validation gate;
do not use it to check behaviour.

Run from the repo root:  python scripts/price_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oyster.invoice import Invoice
from oyster.model import BillingPeriod
from oyster.pricing import price_invoice
from oyster.rules import PricingRules
from oyster.services.customer_directory import CustomerDirectory
from oyster.services.trip_service import TripService


def _print_invoice(invoice: Invoice) -> None:
    print(f"{invoice.customer_name} ({invoice.customer_id}) — {invoice.period_label}")
    print(f"  subtotal:    {invoice.subtotal}")
    print(f"  grand_total: {invoice.grand_total}")
    for cap in invoice.caps:
        print(
            f"  cap[{cap.pool}] band={cap.band} "
            f"bound={cap.bound_level} discount={cap.discount}"
        )


def _print_loyalty(invoice: Invoice) -> None:
    print(
        f"  {invoice.customer_id}: grand_total={invoice.grand_total} "
        f"commuter_club_fee={invoice.commuter_club_fee} "
        f"green_discount={invoice.green_discount}"
    )
    if invoice.upsells:
        for upsell in invoice.upsells:
            print(
                f"    upsell {upsell.programme}: would_have_paid={upsell.would_have_paid} "
                f"saving={upsell.saving}"
            )
    else:
        print("    (no upsells)")


def main() -> None:
    period = BillingPeriod(year=2026, month=4)
    customers = CustomerDirectory()
    trip_service = TripService()
    rules = PricingRules()

    invoices: dict[str, Invoice] = {}
    for customer in customers.all():
        trips = trip_service.trips_for(customer.id, period)
        invoice = price_invoice(customer, period, trips, rules=rules)
        invoices[customer.id] = invoice
        _print_invoice(invoice)
        print()

    print("Loyalty:")
    for invoice in invoices.values():
        _print_loyalty(invoice)


if __name__ == "__main__":
    main()
