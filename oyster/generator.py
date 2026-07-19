"""Adapt an Invoice into the template context and render it.

Two seams live here, kept apart:
- `invoice_to_context` is a pure adapter: Invoice -> the context dict that
  `invoice.html.hbs` consumes.
- `render_invoice_html` is the data-in renderer: customer + plain trips in,
  HTML out, with no external-service access. Callers resolve the customer and
  their trips from the upstream systems (RULES §9) before calling it.
"""

from __future__ import annotations

from pathlib import Path

from oyster.invoice import CapResult, Invoice, InvoiceLine, Upsell
from oyster.model import BillingPeriod, Customer, Programme, Trip
from oyster.money import Money
from oyster.pricing import price_invoice
from oyster.rules import PricingRules
from oyster.template_engine import render_file

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "invoice.html.hbs"

# Single source of truth for programme labels, keyed by programme value string.
# Invoice.enrolled and Upsell.programme both hold Programme.value strings.
_PROGRAMME_LABELS: dict[str, str] = {
    Programme.RAILCARD.value: "Railcard",
    Programme.ZONE_RESIDENT.value: "Zone Resident",
    Programme.COMMUTER_CLUB.value: "Commuter Club",
    Programme.GREEN_TRAVELLER.value: "Green Traveller",
}

_BOUND_LABELS: dict[str | None, str] = {
    "monthly": "Monthly cap",
    "weekly": "Weekly cap",
    "daily": "Daily cap",
    None: "No cap reached",
}


def _programme_label(programme: str) -> str:
    return _PROGRAMME_LABELS[programme]


def _line_context(line: InvoiceLine) -> dict:
    return {
        "date": str(line.date),
        "time": line.time,
        "mode": line.mode,
        "route": line.route,
        "zones": line.zones,
        "peak_label": "Peak" if line.peak else "Off-peak",
        "single_fare": str(line.single_fare),
        "charged": str(line.charged),
        "discounted": line.charged < line.single_fare,
    }


def _cap_context(cap: CapResult) -> dict:
    return {
        "pool_label": "Rail" if cap.pool == "rail" else "Bus & Tram",
        "band": cap.band,
        "bound_label": _BOUND_LABELS[cap.bound_level],
        "discount": str(cap.discount),
        "bound": cap.bound_level is not None,
    }


def _upsell_context(upsell: Upsell) -> dict:
    return {
        "programme_label": _programme_label(upsell.programme),
        "would_have_paid": str(upsell.would_have_paid),
        "saving": str(upsell.saving),
    }


def invoice_to_context(invoice: Invoice) -> dict:
    """Adapt an Invoice into the template's context dict."""
    return {
        "customer_name": invoice.customer_name,
        "customer_id": invoice.customer_id,
        "period_label": invoice.period_label,
        "enrolled": [_programme_label(p) for p in invoice.enrolled],
        "lines": [_line_context(line) for line in invoice.lines],
        "caps": [_cap_context(cap) for cap in invoice.caps],
        "subtotal": str(invoice.subtotal),
        "commuter_club_fee": (
            str(invoice.commuter_club_fee) if invoice.commuter_club_fee > Money.ZERO else None
        ),
        "green_discount": (
            str(invoice.green_discount) if invoice.green_discount > Money.ZERO else None
        ),
        "grand_total": str(invoice.grand_total),
        "upsells": [_upsell_context(upsell) for upsell in invoice.upsells],
    }


def render_invoice_html(
    customer: Customer,
    period: BillingPeriod,
    trips: list[Trip],
    *,
    rules: PricingRules,
) -> str:
    """Price one customer's trips and render the invoice to HTML (data-in seam).

    Pure on its inputs: pricing, context adaptation and template rendering with
    no external-service access.
    """
    invoice = price_invoice(customer, period, trips, rules=rules)
    context = invoice_to_context(invoice)
    return render_file(_TEMPLATE_PATH, context)
