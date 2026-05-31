"""Adapt an Invoice into the template context and orchestrate generation.

Three seams live here, kept apart:
- `invoice_to_context` is a pure adapter: Invoice -> the context dict that
  `invoice.html.hbs` consumes (the exact shape documented in render_demo.py).
- `render_invoice_html` is the data-in renderer: customer + plain trips in,
  HTML out, with no external-service access.
- `generate_invoice_html` is the I/O orchestrator: it queries the services
  (RULES §9) for the customer and trips, then delegates to `render_invoice_html`.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from oyster.invoice import CapResult, Invoice, InvoiceLine, Upsell
from oyster.model import BillingPeriod, Customer, Programme, Trip
from oyster.pricing import price_invoice
from oyster.rules.bank_holidays import BankHolidayService
from oyster.rules.fare_table import FareTable
from oyster.rules.station_registry import StationRegistry
from oyster.services.customer_directory import CustomerDirectory
from oyster.services.trip_service import TripService
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


def _money(value: Decimal) -> str:
    return f"£{value:.2f}"


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
        "single_fare": _money(line.single_fare),
        "charged": _money(line.charged),
        "discounted": line.charged < line.single_fare,
    }


def _cap_context(cap: CapResult) -> dict:
    return {
        "pool_label": "Rail" if cap.pool == "rail" else "Bus & Tram",
        "band": cap.band,
        "bound_label": _BOUND_LABELS[cap.bound_level],
        "discount": _money(cap.discount),
        "bound": cap.bound_level is not None,
    }


def _upsell_context(upsell: Upsell) -> dict:
    return {
        "programme_label": _programme_label(upsell.programme),
        "would_have_paid": _money(upsell.would_have_paid),
        "saving": _money(upsell.saving),
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
        "subtotal": _money(invoice.subtotal),
        "commuter_club_fee": (
            _money(invoice.commuter_club_fee) if invoice.commuter_club_fee > 0 else None
        ),
        "green_discount": (
            _money(invoice.green_discount) if invoice.green_discount > 0 else None
        ),
        "grand_total": _money(invoice.grand_total),
        "upsells": [_upsell_context(upsell) for upsell in invoice.upsells],
    }


def render_invoice_html(
    customer: Customer,
    period: BillingPeriod,
    trips: list[Trip],
    *,
    stations: StationRegistry,
    fares: FareTable,
    holidays: BankHolidayService,
) -> str:
    """Price one customer's trips and render the invoice to HTML (data-in seam).

    Pure on its inputs: pricing, context adaptation and template rendering with
    no external-service access. `generate_invoice_html` is the I/O wrapper.
    """
    invoice = price_invoice(
        customer,
        period,
        trips,
        stations=stations,
        fares=fares,
        bank_holidays=holidays,
    )
    context = invoice_to_context(invoice)
    return render_file(_TEMPLATE_PATH, context)


def generate_invoice_html(
    customer_id: str,
    period: BillingPeriod,
    *,
    customers: CustomerDirectory,
    trips: TripService,
    stations: StationRegistry,
    fares: FareTable,
    holidays: BankHolidayService,
) -> str:
    """Price one customer's invoice and render it to HTML.

    The services are passed explicitly: this is the "queries multiple systems"
    seam from RULES §9. `customer_id` + `period` in, HTML out.
    """
    customer = customers.get(customer_id)
    customer_trips = trips.trips_for(customer_id, period)
    return render_invoice_html(
        customer,
        period,
        customer_trips,
        stations=stations,
        fares=fares,
        holidays=holidays,
    )
