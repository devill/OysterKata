from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from oyster.money import Money


@dataclass(frozen=True)
class InvoiceLine:
    date: date
    time: str  # "HH:MM"
    mode: str  # e.g. "tube"
    route: str  # rail: "From → To"; bus/tram: "—"
    zones: str  # rail: "2" or "1–2"; bus/tram: "—"
    peak: bool
    single_fare: Money  # full fare before any cap/hopper discount
    charged: Money  # final amount billed for this line


@dataclass(frozen=True)
class CapResult:
    pool: str  # "rail" or "bus"
    band: str  # e.g. "Z1-2", "outer", or "—" for bus
    bound_level: str | None  # "daily"/"weekly"/"monthly"/None if no cap reduced the total
    uncapped_sum: Money  # pre-cap pool total (post-hopper for bus)
    discount: Money  # uncapped_sum − final_sum for that pool


@dataclass(frozen=True)
class Upsell:
    programme: str
    would_have_paid: Money
    saving: Money


@dataclass(frozen=True)
class Invoice:
    customer_id: str
    customer_name: str
    period_label: str
    enrolled: tuple[str, ...]
    lines: list[InvoiceLine]
    caps: list[CapResult]
    subtotal: Money  # sum of all charged
    commuter_club_fee: Money  # Money.ZERO when not enrolled in commuter_club
    green_discount: Money  # 5% green_traveller discount, Money.ZERO if inactive
    grand_total: Money  # subtotal + commuter_club_fee − green_discount
    upsells: list[Upsell]
