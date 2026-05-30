# Oyster Kata — Constrained Tests on a Document Generator

A practice exercise for the **[Constrained Tests](https://www.youtube.com/watch?v=GyI5qU9MNJU&t=1578s)**
pattern: putting an *existing, untested* document generator under a test suite
where **code coverage actually means something**.

The system under test is a (fictional) London **Oyster card invoice generator**.
It prices a month of journeys and renders an HTML invoice. The pricing rules are
realistic enough to be genuinely fiddly — and the fiddliness is the point.

> The full domain specification lives in **[`RULES.md`](./RULES.md)**. Read it
> once before you start; you'll refer back to it constantly.

---

## Why this makes a good kata

Coverage is easy to cheat: a test can execute every line of the pricing engine
without asserting that any number is correct. This generator is built to punish
that, because **a single trip's price is not a local fact**:

- **Caps make prices non-local.** Once a daily / weekly / monthly cap is reached,
  later trips that day/week/month are charged £0.00 — so the price printed next
  to a trip depends on *other* trips around it.
- **Hopper** makes a bus tap free because of an *earlier* bus tap.
- **Loyalty** discounts some legs before capping; **commuter club** zeroes whole
  legs and bills a flat fee instead.
- **Upsells** re-price the entire month under a programme the customer *isn't* on,
  so the invoice contains "you'd have saved £X" sections.
- **Zones and boundary stations** mean a leg is priced under whichever zone
  interpretation is cheapest — which then feeds the cap band.

So "assert the grand total" is nowhere near enough. A good test has to pin the
charged amount of *every* line, *every* cap, and *every* upsell — and that is
exactly what a constrained test forces you to do.

---

## The system under test

Inputs are **passed in** (`customer_id`, billing period); everything else is
**queried from separate services** — this is the seam you'll have to get under
control when testing (see RULES §9):

```
                 customer_id, period
                        │
                        ▼
        ┌───────────────────────────────┐     queries
        │   generator.generate_invoice   │ ─────────────▶  CustomerDirectory
        │                                │                 TripService
        │   ┌────────────────────────┐   │                 StationRegistry
        │   │  pricing.compute_invoice│  │                 FareTable
        │   │  fares · caps · loyalty │   │                 BankHolidayService
        │   └────────────────────────┘   │
        │   Invoice ─▶ context dict       │
        │   template_engine.render ──────┐│
        └───────────────────────────────┘│
                        │ invoice.html.hbs ┘
                        ▼
                   HTML invoice
```

| File | Responsibility |
|------|----------------|
| `oyster/model.py` | Domain types (`Trip`, `Customer`, `Mode`, `Programme`, `BillingPeriod`). |
| `oyster/services/*` | Five fake data sources with hard-coded data for four customers. |
| `oyster/pricing.py` | The engine: single fares, Hopper, the daily→weekly→monthly cap cascade with chronological per-line allocation, loyalty programmes, and upsells. **This is the messy code you'll eventually want to refactor.** |
| `oyster/invoice.py` | The `Invoice` result contract. |
| `oyster/template_engine.py` | A small Handlebars-like renderer. |
| `oyster/templates/invoice.html.hbs` | The invoice template. |
| `oyster/generator.py` | Orchestrates services → engine → template; adapts `Invoice` → template context. |
| `oyster/cli.py` | `python -m oyster.cli <id> <YYYY-MM>`. |

There are **four sample customers**, each chosen to exercise a different corner:

| Customer | Exercises |
|----------|-----------|
| `alice`  | A full-month Z1–2 peak commuter — the **daily → weekly → monthly cap cascade** all bind; commuter-club upsell fires. |
| `bob`    | Railcard holder, ≈all off-peak — **enrolled railcard discount** + a green-traveller upsell. |
| `carol`  | Heavy bus user — **Hopper** windows + the **bus daily cap**; zone-resident discount on home-zone rail legs. |
| `dave`   | Commuter-club member using a **boundary station** — in-band legs zeroed + a flat fee line. |

---

## Running it

Requires only Python 3.11+ (no third-party dependencies).

```bash
# Generate one invoice (writes out/<id>_<period>.html)
python -m oyster.cli alice 2026-04

# Generate all four sample invoices
python scripts/generate_all.py

# Inspect the seeded data / intermediate pricing
python scripts/dump_data.py
python scripts/price_demo.py
```

Open the generated file in `out/` in a browser to see the rendered invoice.

> The `scripts/*_demo.py` and `generate_all.py` files are **smoke gates** used
> while building the generator. They are *not* the constrained tests — writing
> those is your job.

---

## The exercise

Your goal: **build a constrained test suite that makes coverage of
`pricing.py` (and the rendered invoice) a trustworthy quality signal.**

The Constrained Tests pattern says: design a *testing DSL* that makes it
**impossible to write a test without sufficient assertions**. Prefer an
**external** DSL (data files + a parser) over a fluent API, because the parser
can *reject an incomplete test specification*.

A suggested shape (this is the "Approved Scenarios" flavour — a human-reviewable
domain format):

1. **Design a fixture format** — one file per scenario — that combines:
   - **input**: a customer + an ordered list of taps (or a reference to one of
     the sample customers);
   - **expected output**: the charged amount for **every** trip line, **every**
     cap result, the totals, and **every** upsell.
2. **Write a parser that refuses incomplete fixtures.** If a fixture omits the
   charged column for any trip, or leaves out the grand total, or a cap row —
   the parser raises and the test errors. This is the constraint: you *cannot*
   land a passing test that asserts nothing.
3. **Write a single data-driven test** that, for each fixture: builds the
   services from the fixture input, runs `generate_invoice_html` /
   `compute_invoice`, and validates **every** value the fixture declares.
4. **Capture the current behaviour as a gold master** for the four sample
   customers (and any edge cases you add), reviewing each expected number by
   hand against `RULES.md`.
5. **Now measure coverage** (`coverage run -m pytest && coverage report`). Because
   the DSL forced full assertions, the covered lines are genuinely *checked*.
6. **Refactor the engine** — `pricing.py` is deliberately tangled — with the gold
   master as your safety net.

### Things worth pinning explicitly
These are where a lazy test would quietly skip the hard logic:

- A capped day: the trip that *crosses* the cap is charged a **partial** fare,
  and every later trip that day is **£0.00**. Pin both.
- Hopper: the second bus tap inside 60 minutes is £0.00; the one just *past* 60
  minutes is charged again (carol has both).
- A loyalty discount that is **fully absorbed by a cap** produces **no upsell
  saving** (alice + zone-resident — see RULES §7b). Don't let this regress.
- Boundary-station tie-break: dave's Stratford (2/3) leg is priced under the
  cheaper zone, which then sets his cap band.

### Stretch goals
- Add a fixture whose *only* difference from another is one tap time crossing a
  peak boundary, and assert the price flips — a regression magnet.
- Mutation-test the suite: change a constant in `FareTable` and confirm a test
  fails. If none does, your DSL isn't constraining enough yet.

---

## Deliberate design notes (so they don't surprise you)

- **No hidden bugs.** The generator is correct per `RULES.md`. The exercise is
  about *locking behaviour before refactoring*, not bug-hunting.
- **The data is fictional.** Station zones and fares are *roughly* TfL-flavoured
  but not real.
- **Caps deviate from real TfL on purpose.** Real weekly caps are ≈5× the daily
  cap, so a 5-day commuter never benefits. Here `weekly ≈ 4.5× daily` and
  `monthly ≈ 3.75× weekly` so the **full cascade is observable and testable**
  (RULES §6a). Without this, the weekly/monthly cap code would be unreachable —
  fatal in a kata about coverage.
- **Determinism.** Everything is seeded; the billing period is fixed to April
  2026 (which includes two bank holidays, both forced off-peak).
