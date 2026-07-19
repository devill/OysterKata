"""Pricing engine for Oyster PAYG invoices.

Pure computation over already-resolved data: callers fetch the customer and
their trips from the upstream systems and hand them in (RULES §9). Only the
deterministic reference data in `oyster.rules` is consulted here, so a pricing
run is reproducible from its arguments alone.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from oyster.invoice import CapResult, Invoice, InvoiceLine, Upsell
from oyster.model import BillingPeriod, Customer, Mode, Programme, Trip
from oyster.money import Money
from oyster.rules import PricingRules

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


# --- Rail-type single fares (RULES §1, §5) -------------------------------------


@dataclass
class _PricedLeg:
    """A single tap after single-fare pricing, before capping."""

    trip: Trip
    pool: str  # "rail" or "bus"
    peak: bool
    route: str
    zones_label: str
    chosen_zones: tuple[int, ...]  # the chosen endpoint zones (rail only)
    includes_zone1: bool
    start_zones: tuple[int, ...]  # zones of the start station (rail only)
    single_fare: Money  # full fare before any loyalty discount / hopper / cap
    pre_cap_charge: Money  # post-loyalty-discount + post-hopper charge fed to capping
    bypass_cap: bool = False  # commuter-club in-band rail legs are charged £0, skip capping


def _zone_label(low: int, high: int) -> str:
    if low == high:
        return str(low)
    return f"{low}–{high}"  # en dash, e.g. "1–2"


def _price_rail_leg(
    trip: Trip, peak: bool, rules: PricingRules
) -> _PricedLeg:
    """Price a rail-type leg, applying the boundary-station tie-break (RULES §1).

    A boundary station maps to two zones. We evaluate the leg under every
    combination of endpoint-zone choices and keep the cheapest single fare. The
    winning combination defines the leg's zones label and band inputs.
    """
    from_zones = rules.stations.zones_for(trip.from_station)
    to_zones = rules.stations.zones_for(trip.to_station)

    best: _PricedLeg | None = None
    for fz in from_zones:
        for tz in to_zones:
            chosen = (fz, tz)
            low = min(chosen)
            high = max(chosen)
            zones_spanned = high - low + 1
            includes_zone1 = low == 1
            fare = Money.of(rules.fares.rail_single(includes_zone1, zones_spanned, peak))
            candidate = _PricedLeg(
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


# --- Bus/tram flat fares + Hopper (RULES §4) -----------------------------------


def _price_flat_leg(trip: Trip, peak: bool, rules: PricingRules) -> _PricedLeg:
    fare = Money.of(rules.fares.flat_fare())
    return _PricedLeg(
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


def _apply_hopper(bus_legs: list[_PricedLeg], rules: PricingRules) -> None:
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


def _rail_band(rail_legs: list[_PricedLeg]) -> str:
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


def _cap_pool(
    legs: list[_PricedLeg],
    daily_cap: Money,
    weekly_cap: Money,
    monthly_cap: Money,
) -> tuple[dict[int, Money], str | None]:
    """Run nested daily/weekly/monthly capping for one pool (RULES §6b–d).

    `legs` must be chronologically ordered and already carry pre_cap_charge
    (post-hopper for bus). They are already period-filtered by the trip service.
    Returns the final per-leg charge keyed by leg id(), plus the most aggressive
    level that actually reduced the pool total.
    """
    final: dict[int, Money] = {}

    # Daily: cap each calendar date independently.
    by_day: dict[date, list[_PricedLeg]] = {}
    for leg in legs:
        by_day.setdefault(leg.trip.touch_in.date(), []).append(leg)
    daily_charge: dict[int, Money] = {}
    for day_legs in by_day.values():
        allocated = _allocate_window([leg.pre_cap_charge for leg in day_legs], daily_cap)
        for leg, charge in zip(day_legs, allocated):
            daily_charge[id(leg)] = charge

    # Weekly: cap each Mon–Sun week, operating on the daily-capped charges.
    by_week: dict[tuple[int, int], list[_PricedLeg]] = {}
    for leg in legs:
        by_week.setdefault(_iso_week_key(leg.trip.touch_in.date()), []).append(leg)
    weekly_charge: dict[int, Money] = {}
    for week_legs in by_week.values():
        allocated = _allocate_window([daily_charge[id(leg)] for leg in week_legs], weekly_cap)
        for leg, charge in zip(week_legs, allocated):
            weekly_charge[id(leg)] = charge

    # Monthly: cap the whole billing period, operating on the weekly-capped charges.
    monthly_allocated = _allocate_window([weekly_charge[id(leg)] for leg in legs], monthly_cap)
    for leg, charge in zip(legs, monthly_allocated):
        final[id(leg)] = charge

    # Determine which level actually reduced the pool total (most aggressive wins).
    uncapped_sum = Money.total(leg.pre_cap_charge for leg in legs)
    daily_sum = Money.total(daily_charge.values())
    weekly_sum = Money.total(weekly_charge.values())
    monthly_sum = Money.total(final.values())
    bound_level: str | None = None
    if daily_sum < uncapped_sum:
        bound_level = "daily"
    if weekly_sum < daily_sum:
        bound_level = "weekly"
    if monthly_sum < weekly_sum:
        bound_level = "monthly"

    return final, bound_level


# --- Loyalty programmes (RULES §7, §7a, §7b) -----------------------------------

_THIRD_MULTIPLIER = Decimal(2) / Decimal(3)  # railcard: −⅓ off
_ZONE_RESIDENT_MULTIPLIER = Decimal("0.75")  # zone_resident: −25%
_GREEN_MULTIPLIER = Decimal("0.95")  # green_traveller: −5%


def _apply_per_leg_discounts(
    rail_legs: list[_PricedLeg], programmes: set[Programme], home_zone: int
) -> None:
    """Apply zone_resident then railcard to rail single fares, before capping.

    Both may apply to the same leg; they compose as multipliers on the full
    single fare. zone_resident discounts legs that START in the home zone (a
    boundary start counts if home_zone is among its zones). railcard discounts
    off-peak legs only. Mutates pre_cap_charge in place; single_fare is left as
    the full undiscounted fare for display.
    """
    zone_resident = Programme.ZONE_RESIDENT in programmes
    railcard = Programme.RAILCARD in programmes
    for leg in rail_legs:
        ratios = []
        if zone_resident and home_zone in leg.start_zones:
            ratios.append(_ZONE_RESIDENT_MULTIPLIER)
        if railcard and not leg.peak:
            ratios.append(_THIRD_MULTIPLIER)
        leg.pre_cap_charge = leg.single_fare.times(*ratios)


def _apply_commuter_club(rail_legs: list[_PricedLeg], band: tuple[int, int]) -> None:
    """Zero in-band rail legs and mark them to bypass capping (RULES §7a).

    A leg is in-band when all its chosen zones fall within the subscribed band.
    Out-of-band rail legs keep their (already-discounted) pre_cap_charge.
    """
    low, high = band
    for leg in rail_legs:
        if leg.chosen_zones and all(low <= z <= high for z in leg.chosen_zones):
            leg.pre_cap_charge = Money.ZERO
            leg.bypass_cap = True


def _reduced_rail_caps(rules: PricingRules, band: str, railcard: bool) -> dict[str, Money]:
    """Rail caps for a run, each reduced by ⅓ when railcard is active (RULES §6a)."""
    caps = {
        level: Money.of(rules.fares.rail_cap(band, level))
        for level in ("daily", "weekly", "monthly")
    }
    if railcard:
        caps = {level: value.times(_THIRD_MULTIPLIER) for level, value in caps.items()}
    return caps


def _fraction_off_peak(priced: list[_PricedLeg]) -> Decimal:
    """Share of all taps in the period that are off-peak (RULES §7)."""
    if not priced:
        return Decimal(0)
    off_peak = sum(1 for leg in priced if not leg.peak)
    return Decimal(off_peak) / Decimal(len(priced))


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
    discounts (zone_resident then railcard) and commuter-club zeroing before
    capping; railcard-reduced caps; then the green_traveller post-cap discount.
    """
    if programmes is None:
        programmes = set(customer.enrolled)

    # 1. Price every leg's single fare (rail tie-break, bus flat) in time order.
    priced: list[_PricedLeg] = []
    for trip in trips:
        peak = _is_peak(trip.touch_in, rules)
        if trip.mode.is_rail_type:
            priced.append(_price_rail_leg(trip, peak, rules))
        else:
            priced.append(_price_flat_leg(trip, peak, rules))

    rail_legs = [leg for leg in priced if leg.pool == "rail"]
    bus_legs = [leg for leg in priced if leg.pool == "bus"]

    # 2. Per-leg loyalty discounts (zone_resident then railcard), before capping.
    _apply_per_leg_discounts(rail_legs, programmes, customer.home_zone)

    # 3. commuter_club zeroes in-band rail legs and removes them from the rail pool.
    commuter_club = Programme.COMMUTER_CLUB in programmes
    commuter_club_fee = Money.ZERO
    if commuter_club:
        band = customer.commuter_club_band
        assert band is not None, "commuter_club enrolment requires a band"
        _apply_commuter_club(rail_legs, band)
        commuter_club_fee = Money.of(customer.commuter_club_fee)

    # 4. Hopper on bus/tram taps, before capping (RULES §4).
    _apply_hopper(bus_legs, rules)

    # 5. Capping per pool (RULES §6). commuter-club in-band legs bypass capping.
    rail_band = _rail_band(rail_legs)
    railcard = Programme.RAILCARD in programmes
    rail_caps = _reduced_rail_caps(rules, rail_band, railcard)
    capped_rail_legs = [leg for leg in rail_legs if not leg.bypass_cap]
    rail_final, rail_bound = _cap_pool(
        capped_rail_legs,
        rail_caps["daily"],
        rail_caps["weekly"],
        rail_caps["monthly"],
    )
    for leg in rail_legs:
        if leg.bypass_cap:
            rail_final[id(leg)] = Money.ZERO
    bus_final, bus_bound = _cap_pool(
        bus_legs,
        Money.of(rules.fares.bus_cap("daily")),
        Money.of(rules.fares.bus_cap("weekly")),
        Money.of(rules.fares.bus_cap("monthly")),
    )
    final_charge = {**rail_final, **bus_final}

    # 6. Assemble invoice lines in original time order. single_fare stays full.
    lines: list[InvoiceLine] = []
    for leg in priced:
        lines.append(
            InvoiceLine(
                date=leg.trip.touch_in.date(),
                time=leg.trip.touch_in.strftime("%H:%M"),
                mode=leg.trip.mode.value,
                route=leg.route,
                zones=leg.zones_label,
                peak=leg.peak,
                single_fare=leg.single_fare,
                charged=final_charge[id(leg)],
            )
        )

    rail_uncapped = Money.total(leg.pre_cap_charge for leg in rail_legs)
    rail_final_sum = Money.total(final_charge[id(leg)] for leg in rail_legs)
    bus_uncapped = Money.total(leg.pre_cap_charge for leg in bus_legs)
    bus_final_sum = Money.total(bus_final.values())

    caps = [
        CapResult(
            pool="rail",
            band=rail_band,
            bound_level=rail_bound,
            uncapped_sum=rail_uncapped,
            discount=rail_uncapped - rail_final_sum,
        ),
        CapResult(
            pool="bus",
            band="—",
            bound_level=bus_bound,
            uncapped_sum=bus_uncapped,
            discount=bus_uncapped - bus_final_sum,
        ),
    ]

    subtotal = Money.total(line.charged for line in lines)

    # 7. green_traveller: −5% on the post-cap total including the commuter-club fee.
    green_active = Programme.GREEN_TRAVELLER in programmes
    pre_green_total = subtotal + commuter_club_fee
    if green_active:
        green_discount = pre_green_total - pre_green_total.times(_GREEN_MULTIPLIER)
    else:
        green_discount = Money.ZERO
    grand_total = subtotal + commuter_club_fee - green_discount

    upsells: list[Upsell] = []
    if _compute_upsells and programmes == set(customer.enrolled):
        upsells = _compute_upsell_list(
            customer,
            period,
            trips,
            rules=rules,
            actual_grand_total=grand_total,
            priced=priced,
        )

    return Invoice(
        customer_id=customer.id,
        customer_name=customer.name,
        period_label=period.label,
        enrolled=tuple(p.value for p in customer.enrolled),
        lines=lines,
        caps=caps,
        subtotal=subtotal,
        commuter_club_fee=commuter_club_fee,
        green_discount=green_discount,
        grand_total=grand_total,
        upsells=upsells,
    )


def _compute_upsell_list(
    customer: Customer,
    period: BillingPeriod,
    trips: list[Trip],
    *,
    rules: PricingRules,
    actual_grand_total: Money,
    priced: list[_PricedLeg],
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
    customer: Customer, priced: list[_PricedLeg]
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
    priced: list[_PricedLeg],
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
