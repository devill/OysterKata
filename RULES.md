# Oyster PAYG Invoicing — Domain Rules

> Canonical, deterministic specification for the legacy invoice generator.
> All money is GBP. All numbers below are fixed reference data the generator
> reads from its services — they are *roughly* TfL-flavoured but deliberately
> tuned to create interaction effects. They are not real TfL fares.

The billing period for the kata is **April 2026**.

---

## 1. Zones & stations

- Zones are **1 through 6**.
- Every station maps to one or more zones via the **Station Registry**.
- **Boundary stations** belong to *two* zones, written `"2/3"`. When a leg
  starts or ends at a boundary station, the fare engine evaluates the leg under
  **each** zone interpretation and keeps the one that is **cheapest for the
  customer** for that leg.

## 2. Modes

| Mode        | Pricing basis                |
|-------------|------------------------------|
| `bus`       | flat fare per tap, no zones  |
| `tram`      | flat fare per tap, no zones  |
| `tube`      | by zones traversed + peak    |
| `overground`| by zones traversed + peak    |
| `dlr`       | by zones traversed + peak    |
| `elizabeth` | by zones traversed + peak    |
| `rail`      | by zones traversed + peak    |

"Rail-type" = everything except `bus`/`tram`.

## 3. Peak / off-peak

Judged by the **touch-in time** of the leg.

- **Peak:** Monday–Friday `06:30–09:30` and `16:00–19:00` (inclusive of start,
  exclusive of end).
- **Off-peak:** all other weekday times, **all** of Saturday/Sunday, and **all**
  of any date the Bank Holiday Service reports as a holiday (treated as a
  weekend for the whole day).

### Bank holidays in scope (April 2026)
- `2026-04-03` Good Friday
- `2026-04-06` Easter Monday

Both fall on weekdays and therefore force off-peak pricing all day.

## 4. Flat fares (bus / tram)

- Flat fare per tap: **£1.75**.
- **Hopper:** any `bus`/`tram` taps within **60 minutes** of the *first* tap of
  a hopper window count as a single fare. The first tap is charged £1.75; every
  later tap inside the window is charged **£0.00**. A tap more than 60 minutes
  after the window's first tap opens a new window.

## 5. Rail-type single fares

Fare depends on **(includes Zone 1?, number of distinct zones spanned, peak?)**.
"Zones spanned" = count of zones in the inclusive range from the lowest to the
highest zone touched on the leg (e.g. Z2→Z4 spans 3 zones: 2,3,4).

### 5a. Journeys that include Zone 1

| Zones spanned | Peak  | Off-peak |
|---------------|-------|----------|
| 1 (Z1 only)   | 2.80  | 2.70     |
| 2             | 3.40  | 2.80     |
| 3             | 3.70  | 2.90     |
| 4             | 4.40  | 2.90     |
| 5             | 5.10  | 3.20     |
| 6             | 5.60  | 3.40     |

### 5b. Journeys that do **not** include Zone 1 (outer)

| Zones spanned | Peak  | Off-peak |
|---------------|-------|----------|
| 1             | 1.90  | 1.70     |
| 2             | 1.90  | 1.70     |
| 3+            | 2.80  | 1.80     |

## 6. Caps

Caps are evaluated as running totals and the **lowest effective charge wins**,
with precedence **monthly > weekly > daily**. Rail-type and bus/tram have
**separate** cap pools.

### 6a. Rail-type caps, by the **widest zone band touched in the period**

The band is the smallest `Z1–N` (or outer band) that covers every rail leg in
the period.

Caps are intentionally set with `weekly ≈ 4.5 × daily` and `monthly ≈ 3.75 ×
weekly` so that a regular 5-day, ~4-week commuter triggers the daily → weekly →
monthly cascade in turn (this is what makes the multi-level capping observable
and testable; real TfL sets weekly ≈ 5 × daily, so a 5-day commuter would not
benefit — we deviate deliberately for the kata).

| Band         | Daily  | Weekly | Monthly |
|--------------|--------|--------|---------|
| Z1–2         | 8.90   | 40.00  | 150.00  |
| Z1–3         | 10.50  | 47.00  | 176.00  |
| Z1–4         | 12.80  | 57.50  | 215.00  |
| Z1–5         | 15.20  | 68.00  | 255.00  |
| Z1–6         | 16.30  | 73.00  | 274.00  |
| Outer (no Z1)| 6.00   | 27.00  | 101.00  |

### 6b. Bus/tram caps (separate pool)

| Daily | Weekly | Monthly |
|-------|--------|---------|
| 5.25  | 26.25  | 105.00  |

### 6c. Cap windows
- **Daily:** a calendar date `00:00–23:59`.
- **Weekly:** **Monday–Sunday**. (April 2026 weeks may be partial at the month
  edges; only taps inside the billing period count.)
- **Monthly:** the billing period.

### 6d. How a cap maps onto individual invoice lines (the idiosyncratic bit)

When a cap clips a window, the discount is allocated **chronologically**:

1. Take that pool's legs in the window in time order.
2. Charge each leg its full single fare, accumulating a running total.
3. The leg that pushes the running total **over** the cap is charged only the
   remainder (`cap − running_total_before_it`), which may be a partial fare.
4. Every later leg in the window is charged **£0.00**.

The same allocation runs at each level; the binding cap (lowest level that is
reached) determines the final per-leg charges. The per-leg `charged` amounts of
a window therefore **sum exactly** to the effective (capped) charge for that
window.

## 7. Loyalty programmes & upsell

A customer may be **enrolled** in zero or more programmes (from the Customer
Directory). Enrolled programmes affect the actual charge. For every programme
the customer is **not** enrolled in (and is eligible for), the invoice prints an
**upsell** section: the whole period is re-priced as if enrolled, and the
section shows `would_have_paid` and `saving = actual_total − would_have_paid`
(only shown when saving > 0).

| Programme        | Effect                                                                 |
|------------------|------------------------------------------------------------------------|
| `railcard`       | ⅓ off **off-peak rail-type single fares**, AND the rail caps (§6a) are reduced by ⅓ for the holder. Peak single fares and bus/tram are untouched. Applied **before** capping. |
| `zone_resident`  | 25% off any **rail-type leg that starts in the customer's home zone** (home zone from the directory; only meaningful for outer home zones). Applied to the single fare **before** capping. |
| `commuter_club`  | Fixed monthly fee buys **unlimited rail-type travel within the subscribed zone band**: in-band rail legs are charged £0; out-of-band rail legs and ALL bus/tram are priced normally. The fee is added as a line. See §7a. |
| `green_traveller`| Eligible only if **≥80% of all taps in the period are off-peak**. Grants a flat **5% discount** on the entire post-cap, post-other-loyalty total. Free to join. |

### 7a. Commuter Club mechanics & standard offer

A leg is **in-band** if all its (tie-break-chosen) zones fall within the
subscribed band. An enrolled holder's invoice = `fee` (a line) + out-of-band
rail charges + bus/tram charges (the latter two still subject to their own
caps/Hopper).

For the **upsell** (a non-enrolled customer), the offered band is the customer's
own rail travel band for the period (§6a band determination) and the fee comes
from this standard offer table (the enrolled holder uses their stored fee):

| Band  | Monthly fee |
|-------|-------------|
| Z1-2  | 130.00      |
| Z1-3  | 150.00      |
| Z1-4  | 190.00      |
| Z1-5  | 230.00      |
| Z1-6  | 260.00      |
| outer | 100.00      |

### 7b. Loyalty application order & upsell computation

Within a single pricing run for a given **active programme set**:
1. Compute each rail-type leg's single fare (with boundary tie-break).
2. Apply `zone_resident` (−25% home-zone legs) then `railcard` (−⅓ off-peak
   legs) to single fares, before capping. (Both may apply to the same leg.)
3. Apply `commuter_club`: zero in-band rail legs (they bypass capping).
4. Run the cap engine (§6) on the remaining rail charges, using railcard-reduced
   caps if `railcard` is active. Bus/tram capping is unaffected by loyalty.
5. Add the commuter-club `fee` line if active.
6. Apply `green_traveller` (−5%) to the resulting total if active.

**Upsell eligibility** (a programme qualifies only when `saving > 0`):
- `railcard`, `zone_resident`, `commuter_club`: eligible whenever not enrolled.
- `green_traveller`: eligible only when not enrolled AND ≥80% of taps off-peak.

Each candidate upsell re-runs the whole engine with that one extra programme
added to the customer's enrolled set, then reports `would_have_paid` and
`saving = actual_grand_total − would_have_paid`.

The invoice shows **only the single highest-saving** qualifying upsell — there is
no point telling a customer about a programme that would save them less. Ties are
broken by programme order: `railcard` > `zone_resident` > `commuter_club` >
`green_traveller`. If no programme saves money, no upsell is shown.

## 8. Invoice contents

The HTML invoice must contain:

1. **Header** — customer name, customer id, billing period, enrolled programmes.
2. **Trip lines** — one row per leg in time order: date, time, mode, route
   (from→to, or "—" for bus/tram), zones touched, peak/off-peak, single fare,
   **charged** amount. Capped/hopper £0.00 lines are shown explicitly.
3. **Caps applied** — for each pool, which cap level bound (if any) and the
   total discount it produced.
4. **Subtotal**, any **commuter-club fee line**, any **green discount**, and
   **grand total**.
5. **Upsell section** — the single highest-saving eligible, non-enrolled
   programme (if any saves money); see §7b.

## 9. Services (data sources)

The generator receives **`customer_id`** and **`billing_period`** as inputs and
queries everything else:

- **Customer Directory** — customer list; per customer: name, home zone,
  enrolled programmes, commuter-club band+fee.
- **Trip Service** — the ordered list of taps for a `(customer_id, period)`.
- **Station Registry** — station → zone(s).
- **Fare Table** — the numbers in sections 4–6.
- **Bank Holiday Service** — holiday dates.

## 10. Sample customers (fake data)

| id      | name           | home zone | enrolled            | commuter club        | profile                                   |
|---------|----------------|-----------|---------------------|----------------------|-------------------------------------------|
| `alice` | Alice Okafor   | 2         | (none)              | —                    | Z1–2 **full-month** peak commuter (~21 working days × 2 legs); rail daily→weekly→**monthly** cap cascade binds; commuter_club upsell fires (PAYG > season ticket) |
| `bob`   | Bob Tremblay   | 4         | `railcard`          | —                    | Z1–4 student, mostly off-peak; green_traveller eligible; railcard already applied |
| `carol` | Carol Nweze    | 5         | `zone_resident`     | —                    | Outer Z4–6, lots of buses (Hopper + bus cap) + outer rail from home zone |
| `dave`  | Dave Lindqvist | 3         | `commuter_club` Z1–3 @ £150 | Z1–3, £150   | Light traveller, uses a 2/3 boundary station; few caps bind |

Trip data per customer is hand-authored, deterministic, and lives in the Trip
Service. It should exercise: peak & off-peak, boundary stations, Hopper windows
(including a tap just outside 60 min), and at least one binding cap.
