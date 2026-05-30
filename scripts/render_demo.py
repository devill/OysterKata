"""Phase 3 gate: render the invoice template with a hand-authored fixture.

Run from the repo root:  python scripts/render_demo.py

This proves two things:
1. The template engine behaves (small inline self-test below).
2. The invoice template renders a realistic invoice covering all of RULES §8,
   written to out/sample_invoice.html.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oyster.template_engine import TemplateError, render, render_file

TEMPLATE_PATH = ROOT / "oyster" / "templates" / "invoice.html.hbs"
OUTPUT_PATH = ROOT / "out" / "sample_invoice.html"


def _self_test() -> None:
    """Cover the engine features the template depends on."""
    # Dotted path.
    assert render("{{a.b}}", {"a": {"b": "deep"}}) == "deep"

    # each with @index, and nested if inside each.
    out = render(
        "{{#each xs}}[{{@index}}:{{this}}{{#if @last}}*{{/if}}]{{/each}}",
        {"xs": ["p", "q"]},
    )
    assert out == "[0:p][1:q*]", out

    # else branch (empty list is falsy).
    assert render("{{#if v}}Y{{else}}N{{/if}}", {"v": []}) == "N"
    assert render("{{#if v}}Y{{else}}N{{/if}}", {"v": [1]}) == "Y"

    # raw vs escaped.
    assert render("{{x}}", {"x": "<b>"}) == "&lt;b&gt;"
    assert render("{{{x}}}", {"x": "<b>"}) == "<b>"

    # missing path -> empty string, no raise.
    assert render("[{{nope}}]", {}) == "[]"

    # fallback to outer context from inside each.
    assert render("{{#each xs}}{{outer}}{{/each}}", {"xs": [1], "outer": "O"}) == "O"

    # malformed template raises.
    raised = False
    try:
        render("{{#each xs}}no close", {"xs": []})
    except TemplateError:
        raised = True
    assert raised, "expected TemplateError for unclosed block"

    print("engine self-test OK")


def _fixture() -> dict:
    return {
        "customer_name": "Alice O'Hara & Co <VIP>",
        "customer_id": "alice",
        "period_label": "April 2026",
        "enrolled": ["Commuter Club"],
        "lines": [
            {
                "date": "2026-04-02",
                "time": "08:10",
                "mode": "tube",
                "route": "Camden Town → Oxford Circus",
                "zones": "1–2",
                "peak_label": "Peak",
                "single_fare": "£3.40",
                "charged": "£3.40",
                "discounted": False,
            },
            {
                "date": "2026-04-02",
                "time": "18:05",
                "mode": "tube",
                "route": "Oxford Circus → Camden Town",
                "zones": "1–2",
                "peak_label": "Peak",
                "single_fare": "£3.40",
                "charged": "£0.00",
                "discounted": True,
            },
            {
                "date": "2026-04-03",
                "time": "12:30",
                "mode": "bus",
                "route": "—",
                "zones": "—",
                "peak_label": "Off-peak",
                "single_fare": "£1.75",
                "charged": "£1.75",
                "discounted": False,
            },
        ],
        "caps": [
            {
                "pool_label": "Rail",
                "band": "Z1-2",
                "bound_label": "Monthly cap",
                "discount": "£40.00",
                "bound": True,
            },
            {
                "pool_label": "Bus & Tram",
                "band": "—",
                "bound_label": "No cap reached",
                "discount": "£0.00",
                "bound": False,
            },
        ],
        "subtotal": "£150.00",
        "commuter_club_fee": "£150.00",
        "green_discount": "£7.59",
        "grand_total": "£292.41",
        "upsells": [
            {
                "programme_label": "Annual Travelcard",
                "would_have_paid": "£270.00",
                "saving": "£22.41",
            },
            {
                "programme_label": "Railcard",
                "would_have_paid": "£280.00",
                "saving": "£12.41",
            },
        ],
    }


def main() -> None:
    _self_test()

    context = _fixture()
    html = render_file(TEMPLATE_PATH, context)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")

    assert "Camden Town" in html, "known route string missing"
    assert "Upsell" in html, "upsell heading missing"
    assert "Monthly cap" in html, "bound cap label missing"
    assert "No cap reached" in html, "non-bound cap label missing"
    assert "£292.41" in html, "grand total missing"
    # HTML-escapable customer name must be escaped, not raw.
    assert "Alice O'Hara & Co <VIP>" not in html, "name should be escaped"
    assert "&amp;" in html and "&lt;VIP&gt;" in html, "escaping not applied"
    # The discounted/£0.00 line is marked.
    assert 'class="saved"' in html, "discounted line not visually marked"

    print(f"wrote {OUTPUT_PATH.relative_to(ROOT)}")
    print("render_demo OK")


if __name__ == "__main__":
    main()
