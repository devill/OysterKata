"""Phase 2a gate: price all four customers for April 2026 and assert invariants.

Run from the repo root:  python scripts/price_demo.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oyster.invoice import Invoice
from oyster.model import BillingPeriod
from oyster.pricing import (
    _allocate_window,
    _iso_week_key,
    _is_peak,
    _price_rail_leg,
    _rail_band,
    compute_invoice,
    default_services,
    money,
)

_ZERO = Decimal("0.00")


def _pool_lines(invoice: Invoice, pool: str):
    rail_modes = {"tube", "overground", "dlr", "elizabeth", "rail"}
    for line in invoice.lines:
        is_rail = line.mode in rail_modes
        if (pool == "rail") == is_rail:
            yield line


def _assert_pool_consistency(invoice: Invoice) -> None:
    for cap in invoice.caps:
        charged_sum = sum((line.charged for line in _pool_lines(invoice, cap.pool)), _ZERO)
        expected = cap.uncapped_sum - cap.discount
        assert charged_sum == expected, (
            f"{invoice.customer_id} {cap.pool}: sum(charged)={charged_sum} "
            f"!= uncapped({cap.uncapped_sum}) - discount({cap.discount})"
        )


def _assert_totals(invoice: Invoice) -> None:
    line_sum = sum((line.charged for line in invoice.lines), _ZERO)
    assert invoice.subtotal == line_sum, (
        f"{invoice.customer_id}: subtotal={invoice.subtotal} != sum(charged)={line_sum}"
    )
    expected_grand = invoice.subtotal + invoice.commuter_club_fee - invoice.green_discount
    assert invoice.grand_total == expected_grand, (
        f"{invoice.customer_id}: grand_total={invoice.grand_total} != subtotal"
        f"({invoice.subtotal}) + commuter_club_fee({invoice.commuter_club_fee}) "
        f"- green_discount({invoice.green_discount}) = {expected_grand}"
    )


def _cap_for(invoice: Invoice, pool: str):
    return next(cap for cap in invoice.caps if cap.pool == pool)


def _upsell_for(invoice: Invoice, programme: str):
    return next((u for u in invoice.upsells if u.programme == programme), None)


def _print_loyalty(invoice: Invoice) -> None:
    print(
        f"  {invoice.customer_id}: grand_total=£{invoice.grand_total} "
        f"commuter_club_fee=£{invoice.commuter_club_fee} "
        f"green_discount=£{invoice.green_discount}"
    )
    if invoice.upsells:
        for u in invoice.upsells:
            print(
                f"    upsell {u.programme}: would_have_paid=£{u.would_have_paid} "
                f"saving=£{u.saving}"
            )
    else:
        print("    (no upsells)")


def _rail_cascade(customer, period, services) -> dict[str, Decimal]:
    """Recompute the rail pool's per-level totals to make the cascade visible.

    Mirrors the engine's nested daily -> weekly -> monthly capping so we can
    print uncapped / post-daily / post-weekly / post-monthly evidence. This is
    illustrative output only; the headline assertions use the engine's Invoice.
    """
    trips = services.trips.trips_for(customer.id, period)
    rail_legs = [
        _price_rail_leg(
            trip,
            _is_peak(trip.touch_in, services.bank_holidays),
            services.stations,
            services.fares,
        )
        for trip in trips
        if trip.mode.is_rail_type
    ]
    band = _rail_band(rail_legs)
    daily_cap = money(services.fares.rail_cap(band, "daily"))
    weekly_cap = money(services.fares.rail_cap(band, "weekly"))
    monthly_cap = money(services.fares.rail_cap(band, "monthly"))

    uncapped = sum((leg.pre_cap_charge for leg in rail_legs), _ZERO)

    by_day: dict[date, list] = defaultdict(list)
    for leg in rail_legs:
        by_day[leg.trip.touch_in.date()].append(leg)
    daily_charge: dict[int, Decimal] = {}
    for day_legs in by_day.values():
        for leg, charge in zip(
            day_legs, _allocate_window([leg.pre_cap_charge for leg in day_legs], daily_cap)
        ):
            daily_charge[id(leg)] = charge

    by_week: dict[tuple[int, int], list] = defaultdict(list)
    for leg in rail_legs:
        by_week[_iso_week_key(leg.trip.touch_in.date())].append(leg)
    weekly_charge: dict[int, Decimal] = {}
    for week_legs in by_week.values():
        for leg, charge in zip(
            week_legs, _allocate_window([daily_charge[id(leg)] for leg in week_legs], weekly_cap)
        ):
            weekly_charge[id(leg)] = charge

    monthly = _allocate_window([weekly_charge[id(leg)] for leg in rail_legs], monthly_cap)

    return {
        "uncapped": uncapped,
        "post_daily": sum(daily_charge.values(), _ZERO),
        "post_weekly": sum(weekly_charge.values(), _ZERO),
        "post_monthly": sum(monthly, _ZERO),
    }


def main() -> None:
    period = BillingPeriod(year=2026, month=4)
    services = default_services()

    invoices: dict[str, Invoice] = {}
    for customer in services.customers.all():
        invoice = compute_invoice(customer, period, services)
        invoices[customer.id] = invoice

        print(f"{invoice.customer_name} ({invoice.customer_id}) — {invoice.period_label}")
        print(f"  subtotal:    £{invoice.subtotal}")
        print(f"  grand_total: £{invoice.grand_total}")
        for cap in invoice.caps:
            print(
                f"  cap[{cap.pool}] band={cap.band} "
                f"bound={cap.bound_level} discount=£{cap.discount}"
            )
        print()

        # Per-pool consistency and total invariants are hard gates — these
        # MUST hold regardless of the trip data.
        _assert_pool_consistency(invoice)
        _assert_totals(invoice)

    print("Money invariants passed for all customers.\n")

    # The data must actually exercise the cap engine (RULES requires at least one
    # binding cap). alice's rail cap and carol's bus cap are both expected to bind.
    alice_rail = _cap_for(invoices["alice"], "rail")
    carol_bus = _cap_for(invoices["carol"], "bus")

    data_problems: list[str] = []
    if alice_rail.bound_level is None:
        data_problems.append("alice's RAIL cap did not bind — expected it to exercise the rail cap engine.")
    else:
        print(
            f"  alice rail cap bound at: {alice_rail.bound_level} "
            f"(discount £{alice_rail.discount})"
        )
    if carol_bus.bound_level is None:
        data_problems.append("carol's BUS cap did not bind — expected it to exercise the bus cap engine.")
    else:
        print(f"  carol bus cap bound at:  {carol_bus.bound_level} (discount £{carol_bus.discount})")

    if data_problems:
        print("\nDATA PROBLEM (NOT altering trip data — flagging instead):")
        for problem in data_problems:
            print(f"  - {problem}")
        sys.exit(1)

    # alice's rail cap cascade evidence (daily -> weekly -> monthly).
    alice = next(c for c in services.customers.all() if c.id == "alice")
    cascade = _rail_cascade(alice, period, services)
    print("\n  alice rail cap cascade (daily -> weekly -> monthly):")
    print(f"    uncapped rail total: £{cascade['uncapped']}")
    print(f"    post-daily total:    £{cascade['post_daily']}")
    print(f"    post-weekly total:   £{cascade['post_weekly']}")
    print(f"    post-monthly total:  £{cascade['post_monthly']}")

    # Headline assertions use the engine's actual Invoice output.
    alice_invoice = invoices["alice"]
    expected_monthly = Decimal("150.00")
    assert alice_rail.bound_level == "monthly", (
        f"alice rail cap bound at {alice_rail.bound_level!r}, expected 'monthly'."
    )
    # No bus/loyalty for alice in 2a, so the rail-pool charged total == grand_total.
    assert alice_invoice.grand_total == expected_monthly, (
        f"alice grand_total={alice_invoice.grand_total}, expected £{expected_monthly} "
        f"(rail monthly cap)."
    )
    print(
        f"\n  alice rail cap binds at MONTHLY, grand_total = £{alice_invoice.grand_total}."
    )

    assert carol_bus.bound_level == "daily", (
        f"carol bus cap bound at {carol_bus.bound_level!r}, expected 'daily'."
    )

    # --- Phase 2b: loyalty programmes & upsells ------------------------------
    print("\nLoyalty (actual invoices):")
    for cid in ("alice", "bob", "carol", "dave"):
        _print_loyalty(invoices[cid])

    customers = {c.id: c for c in services.customers.all()}

    # Every customer: grand_total == subtotal + commuter_club_fee − green_discount.
    for invoice in invoices.values():
        expected = invoice.subtotal + invoice.commuter_club_fee - invoice.green_discount
        assert invoice.grand_total == expected, (
            f"{invoice.customer_id}: grand_total={invoice.grand_total} != "
            f"subtotal+fee-green={expected}"
        )

    # bob: railcard holder, ~all off-peak. His railcard makes him strictly
    # cheaper than with no programmes, and he gets a green_traveller upsell.
    bob = customers["bob"]
    bob_no_prog = compute_invoice(bob, period, services, programmes=set())
    assert invoices["bob"].grand_total < bob_no_prog.grand_total, (
        f"bob railcard grand_total={invoices['bob'].grand_total} not < "
        f"no-programmes={bob_no_prog.grand_total}"
    )
    bob_green = _upsell_for(invoices["bob"], "green_traveller")
    assert bob_green is not None and bob_green.saving > _ZERO, (
        "bob expected a green_traveller upsell with saving > 0"
    )
    print(
        f"\n  bob railcard: £{invoices['bob'].grand_total} < no-programmes "
        f"£{bob_no_prog.grand_total}; green upsell saving £{bob_green.saving}."
    )

    # alice: not enrolled; commuter_club upsell is the Z1-2 standard offer (£130),
    # fully in-band with no bus, so saving = £150.00 − £130.00 = £20.00.
    alice_cc = _upsell_for(invoices["alice"], "commuter_club")
    assert alice_cc is not None, "alice expected a commuter_club upsell"
    assert alice_cc.would_have_paid == Decimal("130.00"), (
        f"alice commuter_club would_have_paid={alice_cc.would_have_paid}, expected 130.00"
    )
    assert alice_cc.saving == Decimal("20.00"), (
        f"alice commuter_club saving={alice_cc.saving}, expected 20.00"
    )
    print(
        f"  alice commuter_club upsell: would_have_paid=£{alice_cc.would_have_paid} "
        f"saving=£{alice_cc.saving}."
    )
    # alice correctly has NO zone_resident upsell. Her morning legs DO get the
    # −25% home-zone discount on their single fares, but her rail spend is capped
    # at the £150.00 monthly cap regardless, so the discount is fully absorbed by
    # the cap and the grand_total is unchanged (saving £0). Per RULES §7b an upsell
    # is offered only when saving > 0, so omitting it is the correct engine behaviour.

    # carol: zone_resident enrolled (home zone 5); at least one rail leg is
    # charged below its full single fare because of the −25% discount.
    carol_inv = invoices["carol"]
    rail_modes = {"tube", "overground", "dlr", "elizabeth", "rail"}
    discounted = [
        line
        for line in carol_inv.lines
        if line.mode in rail_modes and line.charged < line.single_fare
    ]
    assert discounted, (
        "carol expected at least one rail leg charged below its single fare "
        "(zone_resident −25%)"
    )
    print(
        f"  carol zone_resident: {len(discounted)} rail leg(s) charged below single "
        f"fare, e.g. {discounted[0].time} £{discounted[0].charged} < £{discounted[0].single_fare}."
    )

    # dave: commuter_club Z1-3 @ £150. Fee line £150.00, in-band rail legs £0.00,
    # grand_total = £150.00 + out-of-band/bus charges.
    dave_inv = invoices["dave"]
    assert dave_inv.commuter_club_fee == Decimal("150.00"), (
        f"dave commuter_club_fee={dave_inv.commuter_club_fee}, expected 150.00"
    )
    in_band_rail = [
        line for line in dave_inv.lines if line.mode in rail_modes and line.charged == _ZERO
    ]
    assert in_band_rail, "dave expected in-band rail legs charged £0.00"
    non_fee_charges = sum((line.charged for line in dave_inv.lines), _ZERO)
    assert dave_inv.grand_total == Decimal("150.00") + non_fee_charges, (
        f"dave grand_total={dave_inv.grand_total} != 150.00 + other charges "
        f"{non_fee_charges}"
    )
    print(
        f"  dave commuter_club: fee=£{dave_inv.commuter_club_fee}, "
        f"{len(in_band_rail)} in-band rail leg(s) at £0.00, "
        f"grand_total=£{dave_inv.grand_total} (= 150.00 + £{non_fee_charges})."
    )

    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()
