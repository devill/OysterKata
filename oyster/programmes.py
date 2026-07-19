"""Loyalty programme discount rules (RULES §7, §7a, §7b).

Each programme is a strategy that hooks into the pricing phases it affects;
the hooks it does not use fall back to "no effect". `ProgrammeDiscounts`
composes an enrolment set into one façade, so the pricing engine never branches
on which programmes are active.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from oyster.model import Customer, Programme
from oyster.money import Money
from oyster.priced_leg import PricedLeg

_NO_CHANGE = Decimal(1)
_THIRD_OFF = Decimal(2) / Decimal(3)
_QUARTER_OFF = Decimal("0.75")
_TWENTIETH_OFF = Decimal("0.95")


class ProgrammeDiscount:
    """One programme's effect on pricing. Every hook defaults to no effect."""

    def single_fare_ratio(self, leg: PricedLeg) -> Decimal:
        return _NO_CHANGE

    def waives(self, leg: PricedLeg) -> bool:
        return False

    def cap_ratio(self) -> Decimal:
        return _NO_CHANGE

    def subscription_fee(self) -> Money:
        return Money.ZERO

    def total_ratio(self) -> Decimal:
        return _NO_CHANGE


class Railcard(ProgrammeDiscount):
    """−⅓ on off-peak rail singles and on every rail cap (RULES §6a, §7)."""

    def single_fare_ratio(self, leg: PricedLeg) -> Decimal:
        return _NO_CHANGE if leg.peak else _THIRD_OFF

    def cap_ratio(self) -> Decimal:
        return _THIRD_OFF


@dataclass(frozen=True)
class ZoneResident(ProgrammeDiscount):
    """−25% on rail legs starting in the customer's home zone (RULES §7).

    A boundary start counts when the home zone is among its zones.
    """

    home_zone: int

    def single_fare_ratio(self, leg: PricedLeg) -> Decimal:
        if self.home_zone in leg.start_zones:
            return _QUARTER_OFF
        return _NO_CHANGE


@dataclass(frozen=True)
class CommuterClub(ProgrammeDiscount):
    """Rail legs inside the subscribed band travel free for a flat fee (RULES §7a).

    A leg is in-band when all its chosen zones fall within the band; out-of-band
    legs keep their charge and go through capping as usual.
    """

    band: tuple[int, int]
    fee: Money

    def waives(self, leg: PricedLeg) -> bool:
        low, high = self.band
        return bool(leg.chosen_zones) and all(low <= zone <= high for zone in leg.chosen_zones)

    def subscription_fee(self) -> Money:
        return self.fee


class GreenTraveller(ProgrammeDiscount):
    """−5% on the post-cap total, including the commuter-club fee (RULES §7)."""

    def total_ratio(self) -> Decimal:
        return _TWENTIETH_OFF


@dataclass(frozen=True)
class ProgrammeDiscounts:
    """The composed effect of everything a customer is enrolled in."""

    discounts: tuple[ProgrammeDiscount, ...]

    def discounted_fare(self, leg: PricedLeg) -> Money:
        return leg.single_fare.times(*(d.single_fare_ratio(leg) for d in self.discounts))

    def waives(self, leg: PricedLeg) -> bool:
        return any(d.waives(leg) for d in self.discounts)

    def discounted_cap(self, cap: Money) -> Money:
        return cap.times(*(d.cap_ratio() for d in self.discounts))

    def subscription_fee(self) -> Money:
        return Money.total(d.subscription_fee() for d in self.discounts)

    def discount_on_total(self, total: Money) -> Money:
        return total - total.times(*(d.total_ratio() for d in self.discounts))


def discounts_for(programmes: set[Programme], customer: Customer) -> ProgrammeDiscounts:
    """Build the discounts for an enrolment set, in the order RULES §7b mandates."""
    builders = (
        (Programme.ZONE_RESIDENT, lambda: ZoneResident(customer.home_zone)),
        (Programme.RAILCARD, Railcard),
        (Programme.COMMUTER_CLUB, lambda: _commuter_club(customer)),
        (Programme.GREEN_TRAVELLER, GreenTraveller),
    )
    return ProgrammeDiscounts(
        tuple(build() for programme, build in builders if programme in programmes)
    )


def _commuter_club(customer: Customer) -> CommuterClub:
    band = customer.commuter_club_band
    fee = customer.commuter_club_fee
    assert band is not None and fee is not None, "commuter_club enrolment requires a band and fee"
    return CommuterClub(band=band, fee=Money.of(fee))
