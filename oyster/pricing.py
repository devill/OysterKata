"""Pricing engine for Oyster PAYG invoices.

Pure computation over already-resolved data: callers fetch the customer and
their trips from the upstream systems and hand them in (RULES §9). Only the
deterministic reference data in `oyster.rules` is consulted here, so a pricing
run is reproducible from its arguments alone.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from oyster.invoice import Invoice, Upsell
from oyster.invoice_builder import CappedPool, InvoiceBuilder
from oyster.model import BillingPeriod, Customer, Mode, Programme, Trip
from oyster.money import Money
from oyster.priced_leg import PricedLeg
from oyster.programmes import ProgrammeDiscounts, discounts_for
from oyster.rules import PricingRules

_CAP_LEVELS = ("daily", "weekly", "monthly")


# --- Peak / off-peak (RULES §3) ------------------------------------------------

_PEAK_MORNING = (timedelta(hours=6, minutes=30), timedelta(hours=9, minutes=30))
_PEAK_EVENING = (timedelta(hours=16), timedelta(hours=19))


def _is_peak(touch_in: datetime, rules: PricingRules) -> bool:
    d = touch_in.date()
    if rules.bank_holidays.is_holiday(d):
        return False
    if d.weekday() >= 5:  # Saturday/Sunday
        return False
    since_midnight = timedelta(hours=touch_in.hour, minutes=touch_in.minute)
    for start, end in (_PEAK_MORNING, _PEAK_EVENING):
        if start <= since_midnight < end:  # inclusive start, exclusive end
            return True
    return False


# --- Single fares (RULES §1, §4, §5) -------------------------------------------


def _zone_label(low: int, high: int) -> str:
    if low == high:
        return str(low)
    return f"{low}–{high}"  # en dash, e.g. "1–2"


def _price_leg(trip: Trip, rules: PricingRules) -> PricedLeg:
    peak = _is_peak(trip.touch_in, rules)
    if trip.mode.is_rail_type:
        return _price_rail_leg(trip, peak, rules)
    return _price_flat_leg(trip, peak, rules)


def _price_rail_leg(trip: Trip, peak: bool, rules: PricingRules) -> PricedLeg:
    """Price a rail-type leg, applying the boundary-station tie-break (RULES §1).

    A boundary station maps to two zones. We evaluate the leg under every
    combination of endpoint-zone choices and keep the cheapest single fare. The
    winning combination defines the leg's zones label and band inputs.
    """
    from_zones = rules.stations.zones_for(trip.from_station)
    to_zones = rules.stations.zones_for(trip.to_station)

    best: PricedLeg | None = None
    for fz in from_zones:
        for tz in to_zones:
            chosen = (fz, tz)
            low = min(chosen)
            high = max(chosen)
            zones_spanned = high - low + 1
            includes_zone1 = low == 1
            fare = Money.of(rules.fares.rail_single(includes_zone1, zones_spanned, peak))
            candidate = PricedLeg(
                trip=trip,
                pool="rail",
                peak=peak,
                route=f"{trip.from_station} → {trip.to_station}",
                zones_label=_zone_label(low, high),
                chosen_zones=tuple(sorted(set(chosen))),
                includes_zone1=includes_zone1,
                start_zones=from_zones,
                single_fare=fare,
                pre_cap_charge=fare,
            )
            if best is None or candidate.single_fare < best.single_fare:
                best = candidate
    assert best is not None
    return best


def _price_flat_leg(trip: Trip, peak: bool, rules: PricingRules) -> PricedLeg:
    fare = Money.of(rules.fares.flat_fare())
    return PricedLeg(
        trip=trip,
        pool="bus",
        peak=peak,
        route="—",
        zones_label="—",
        chosen_zones=(),
        includes_zone1=False,
        start_zones=(),
        single_fare=fare,
        pre_cap_charge=fare,  # adjusted by _apply_hopper
    )


def _apply_hopper(bus_legs: list[PricedLeg], rules: PricingRules) -> None:
    """Zero out flat-fare taps inside a 60-minute hopper window (RULES §4).

    Taps are processed chronologically. A tap within the window of the window's
    FIRST tap is charged £0.00; the first tap at or beyond the window opens a
    new window. Mutates each leg's pre_cap_charge in place. Hopper runs BEFORE
    capping, so a zeroed tap enters capping already at £0.00.
    """
    window = timedelta(minutes=rules.fares.hopper_window_minutes())
    window_start: datetime | None = None
    for leg in bus_legs:  # caller passes these in chronological order
        tap = leg.trip.touch_in
        if window_start is None or tap - window_start >= window:
            window_start = tap
            leg.pre_cap_charge = leg.single_fare
        else:
            leg.pre_cap_charge = Money.ZERO


# --- Cap engine (RULES §6) -----------------------------------------------------


def _rail_band(rail_legs: list[PricedLeg]) -> str:
    """Widest zone band touched by rail legs in the period (RULES §6a).

    If any rail leg's chosen zones include zone 1, band = Z1-N where N is the
    max chosen zone across all rail legs; otherwise band = "outer".
    """
    if not rail_legs:
        return "outer"
    includes_zone1 = any(leg.includes_zone1 for leg in rail_legs)
    if not includes_zone1:
        return "outer"
    max_zone = max(z for leg in rail_legs for z in leg.chosen_zones)
    # Zone-1-only journeys have no separate cap; they fall under the Z1-2
    # floor (human-requested fix — there is no "Z1-1" cap band).
    return f"Z1-{max(max_zone, 2)}"


def _allocate_window(charges: list[Money], cap: Money) -> list[Money]:
    """Allocate a cap across a window's charges chronologically (RULES §6d).

    Accumulate full charges in time order; the charge that pushes the running
    total over the cap is reduced to the remainder; every later charge becomes
    £0.00. If the window never exceeds the cap, charges are returned unchanged.
    """
    if Money.total(charges) <= cap:
        return list(charges)
    allocated: list[Money] = []
    running = Money.ZERO
    capped = False
    for charge in charges:
        if capped:
            allocated.append(Money.ZERO)
            continue
        if running + charge <= cap:
            allocated.append(charge)
            running = running + charge
        else:
            allocated.append(cap - running)
            running = cap
            capped = True
    return allocated


def _iso_week_key(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return (iso.year, iso.week)


def _day_of(leg: PricedLeg) -> Hashable:
    return leg.trip.touch_in.date()


def _week_of(leg: PricedLeg) -> Hashable:
    return _iso_week_key(leg.trip.touch_in.date())


def _period_of(leg: PricedLeg) -> Hashable:
    return "period"  # the whole billing period is a single window


def _allocate_by_window(
    legs: list[PricedLeg],
    window_of: Callable[[PricedLeg], Hashable],
    charges: list[Money],
    cap: Money,
) -> list[Money]:
    """Cap each window independently, returning charges aligned with `legs`."""
    windows: dict[Hashable, list[int]] = {}
    for index, leg in enumerate(legs):
        windows.setdefault(window_of(leg), []).append(index)
    allocated = list(charges)
    for indexes in windows.values():
        window_charges = _allocate_window([charges[index] for index in indexes], cap)
        for index, charge in zip(indexes, window_charges):
            allocated[index] = charge
    return allocated


def _cap_pool(legs: list[PricedLeg], caps: dict[str, Money]) -> str | None:
    """Run nested daily/weekly/monthly capping for one pool (RULES §6b–d).

    `legs` must be chronologically ordered and already carry pre_cap_charge
    (post-hopper for bus). They are already period-filtered by the caller. Each
    level caps the previous level's charges over a wider window. Sets each leg's
    final `charged` and returns the most aggressive level that actually reduced
    the pool total.
    """
    uncapped = [leg.pre_cap_charge for leg in legs]
    daily = _allocate_by_window(legs, _day_of, uncapped, caps["daily"])
    weekly = _allocate_by_window(legs, _week_of, daily, caps["weekly"])
    monthly = _allocate_by_window(legs, _period_of, weekly, caps["monthly"])
    for leg, charge in zip(legs, monthly):
        leg.charged = charge
    return _bound_level([uncapped, daily, weekly, monthly])


def _bound_level(stages: list[list[Money]]) -> str | None:
    """The most aggressive cap level that reduced the pool total, if any."""
    totals = [Money.total(stage) for stage in stages]
    bound: str | None = None
    for level, total, previous in zip(_CAP_LEVELS, totals[1:], totals):
        if total < previous:
            bound = level
    return bound


def _fraction_off_peak(priced: list[PricedLeg]) -> Decimal:
    """Share of all taps in the period that are off-peak (RULES §7)."""
    if not priced:
        return Decimal(0)
    off_peak = sum(1 for leg in priced if not leg.peak)
    return Decimal(off_peak) / Decimal(len(priced))


def _cap_rail_pool(
    rail_legs: list[PricedLeg], rules: PricingRules, discounts: ProgrammeDiscounts
) -> CappedPool:
    """Cap the rail pool at its band's caps; commuter-club in-band legs bypass it."""
    band = _rail_band(rail_legs)
    caps = {
        level: discounts.discounted_cap(Money.of(rules.fares.rail_cap(band, level)))
        for level in _CAP_LEVELS
    }
    bound_level = _cap_pool([leg for leg in rail_legs if not leg.bypass_cap], caps)
    for leg in rail_legs:
        if leg.bypass_cap:
            leg.charged = Money.ZERO
    return CappedPool(name="rail", band=band, legs=rail_legs, bound_level=bound_level)


def _cap_bus_pool(bus_legs: list[PricedLeg], rules: PricingRules) -> CappedPool:
    caps = {level: Money.of(rules.fares.bus_cap(level)) for level in _CAP_LEVELS}
    bound_level = _cap_pool(bus_legs, caps)
    return CappedPool(name="bus", band="—", legs=bus_legs, bound_level=bound_level)


# --- Engine entry point --------------------------------------------------------


def price_invoice(
    customer: Customer,
    period: BillingPeriod,
    trips: list[Trip],
    *,
    rules: PricingRules,
    programmes: set[Programme] | None = None,
    _compute_upsells: bool = True,
) -> Invoice:
    """Compute an invoice from plain trip data over a billing period.

    `programmes=None` uses `customer.enrolled` (the ACTUAL invoice). Passing an
    explicit programme set re-prices "as if enrolled in exactly that set", which
    upsell computation relies on. `_compute_upsells` is an internal recursion
    guard: upsell re-runs never recurse into computing further upsells.

    Loyalty effects are applied in the order mandated by RULES §7b: per-leg
    discounts and commuter-club waiving before capping; railcard-reduced caps;
    then the green_traveller post-cap discount.
    """
    if programmes is None:
        programmes = set(customer.enrolled)
    discounts = discounts_for(programmes, customer)

    # 1. Price every leg's single fare (rail tie-break, bus flat) in time order.
    legs = [_price_leg(trip, rules) for trip in trips]
    rail_legs = [leg for leg in legs if leg.pool == "rail"]
    bus_legs = [leg for leg in legs if leg.pool == "bus"]

    # 2. Per-leg loyalty discounts, then commuter-club waiving, before capping.
    _apply_leg_discounts(rail_legs, discounts)
    _waive_in_band_legs(rail_legs, discounts)

    # 3. Hopper on bus/tram taps, also before capping (RULES §4).
    _apply_hopper(bus_legs, rules)

    # 4. Capping per pool (RULES §6), then assemble the invoice.
    pools = [_cap_rail_pool(rail_legs, rules, discounts), _cap_bus_pool(bus_legs, rules)]
    invoice = InvoiceBuilder(customer, period, legs, pools, discounts).build()

    if _compute_upsells and programmes == set(customer.enrolled):
        invoice = replace(
            invoice,
            upsells=_compute_upsell_list(
                customer,
                period,
                trips,
                rules=rules,
                actual_grand_total=invoice.grand_total,
                priced=legs,
            ),
        )
    return invoice


def _apply_leg_discounts(rail_legs: list[PricedLeg], discounts: ProgrammeDiscounts) -> None:
    """Discount each rail single fare, leaving single_fare intact for display."""
    for leg in rail_legs:
        leg.pre_cap_charge = discounts.discounted_fare(leg)


def _waive_in_band_legs(rail_legs: list[PricedLeg], discounts: ProgrammeDiscounts) -> None:
    """Zero waived rail legs and mark them to bypass capping (RULES §7a)."""
    for leg in rail_legs:
        if discounts.waives(leg):
            leg.pre_cap_charge = Money.ZERO
            leg.bypass_cap = True


def _compute_upsell_list(
    customer: Customer,
    period: BillingPeriod,
    trips: list[Trip],
    *,
    rules: PricingRules,
    actual_grand_total: Money,
    priced: list[PricedLeg],
) -> list[Upsell]:
    """Build the single highest-saving upsell for the ACTUAL invoice (RULES §7b).

    For each programme the customer is not enrolled in and is eligible for,
    re-price with that one extra programme and keep the candidate only if it
    saves money. The commuter_club upsell offers the customer's own rail band at
    the standard-offer fee. Of all qualifying candidates, only the one with the
    maximum saving is returned (as a single-element list); ties are broken by
    programme order (railcard > zone_resident > commuter_club > green_traveller).
    Returns an empty list when nothing qualifies.
    """
    eligible = _eligible_upsell_programmes(customer, priced)
    upsells: list[Upsell] = []
    for programme in (
        Programme.RAILCARD,
        Programme.ZONE_RESIDENT,
        Programme.COMMUTER_CLUB,
        Programme.GREEN_TRAVELLER,
    ):
        if programme not in eligible:
            continue
        upsell_customer = _customer_for_upsell(customer, programme, priced, rules)
        re_run = price_invoice(
            customer=upsell_customer,
            period=period,
            trips=trips,
            rules=rules,
            programmes=set(customer.enrolled) | {programme},
            _compute_upsells=False,
        )
        saving = actual_grand_total - re_run.grand_total
        if saving > Money.ZERO:
            upsells.append(
                Upsell(
                    programme=programme.value,
                    would_have_paid=re_run.grand_total,
                    saving=saving,
                )
            )
    if not upsells:
        return []
    return [max(upsells, key=lambda u: u.saving)]


def _eligible_upsell_programmes(
    customer: Customer, priced: list[PricedLeg]
) -> set[Programme]:
    enrolled = set(customer.enrolled)
    eligible: set[Programme] = set()
    for programme in (Programme.RAILCARD, Programme.ZONE_RESIDENT, Programme.COMMUTER_CLUB):
        if programme not in enrolled:
            eligible.add(programme)
    if Programme.GREEN_TRAVELLER not in enrolled:
        if _fraction_off_peak(priced) >= Decimal("0.8"):
            eligible.add(Programme.GREEN_TRAVELLER)
    return eligible


def _customer_for_upsell(
    customer: Customer,
    programme: Programme,
    priced: list[PricedLeg],
    rules: PricingRules,
) -> Customer:
    """Return the customer to re-price for an upsell run.

    Only commuter_club needs synthetic fields: the offered band is the
    customer's own rail band for the period and the fee is the standard offer.
    """
    if programme != Programme.COMMUTER_CLUB:
        return customer
    rail_legs = [leg for leg in priced if leg.pool == "rail"]
    band_label = _rail_band(rail_legs)
    if band_label == "outer":
        chosen_zones = [z for leg in rail_legs for z in leg.chosen_zones]
        low = min(chosen_zones, default=2)
        high = max(chosen_zones, default=6)
        offered_band = (low, high)
    else:
        high = int(band_label.split("-")[1])
        offered_band = (1, high)
    fee = rules.fares.commuter_club_fee(band_label)
    return replace(customer, commuter_club_band=offered_band, commuter_club_fee=fee)
