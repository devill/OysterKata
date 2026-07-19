"""Assemble a priced, capped billing period into an Invoice."""

from __future__ import annotations

from dataclasses import dataclass

from oyster.invoice import CapResult, Invoice, InvoiceLine
from oyster.model import BillingPeriod, Customer
from oyster.money import Money
from oyster.priced_leg import PricedLeg
from oyster.programmes import ProgrammeDiscounts


@dataclass(frozen=True)
class CappedPool:
    """One capping pool's outcome: its legs, its band and the level that bound."""

    name: str  # "rail" or "bus"
    band: str  # e.g. "Z1-2", "outer", or "—" for bus
    legs: list[PricedLeg]
    bound_level: str | None

    def cap_result(self) -> CapResult:
        uncapped_sum = Money.total(leg.pre_cap_charge for leg in self.legs)
        final_sum = Money.total(leg.charged for leg in self.legs)
        return CapResult(
            pool=self.name,
            band=self.band,
            bound_level=self.bound_level,
            uncapped_sum=uncapped_sum,
            discount=uncapped_sum - final_sum,
        )


@dataclass(frozen=True)
class InvoiceBuilder:
    """Turns the pricing engine's output into the Invoice the renderer consumes.

    Lines keep the original tap order and show the full single fare alongside
    what was actually charged.
    """

    customer: Customer
    period: BillingPeriod
    legs: list[PricedLeg]
    pools: list[CappedPool]
    discounts: ProgrammeDiscounts

    def build(self) -> Invoice:
        lines = [_invoice_line(leg) for leg in self.legs]
        subtotal = Money.total(line.charged for line in lines)
        subscription_fee = self.discounts.subscription_fee()
        green_discount = self.discounts.discount_on_total(subtotal + subscription_fee)
        return Invoice(
            customer_id=self.customer.id,
            customer_name=self.customer.name,
            period_label=self.period.label,
            enrolled=tuple(programme.value for programme in self.customer.enrolled),
            lines=lines,
            caps=[pool.cap_result() for pool in self.pools],
            subtotal=subtotal,
            commuter_club_fee=subscription_fee,
            green_discount=green_discount,
            grand_total=subtotal + subscription_fee - green_discount,
            upsells=[],
        )


def _invoice_line(leg: PricedLeg) -> InvoiceLine:
    return InvoiceLine(
        date=leg.trip.touch_in.date(),
        time=leg.trip.touch_in.strftime("%H:%M"),
        mode=leg.trip.mode.value,
        route=leg.route,
        zones=leg.zones_label,
        peak=leg.peak,
        single_fare=leg.single_fare,
        charged=leg.charged,
    )
