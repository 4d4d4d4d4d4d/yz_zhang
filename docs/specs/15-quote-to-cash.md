# Spec 15 — Quote-to-Cash Logic (CPQ · Revenue Recognition · Metering)

Status: **Approved** · Review: R1 (2026-07-04)
Domains: `logic/cpq.js`, `logic/revrec.js`, `logic/metering.js`

## Problem

The PR #4 base-branch merge brought in ten console modules from a
parallel session, three of which carry real commercial math inline and
untested — quote pricing with an approval matrix, ASC-606-style revenue
recognition schedules, and usage-overage billing. Per spec 13 policy,
they move to the logic layer with specs and tests before further work
builds on them.

## Design — `cpq.js`

### `priceQuote(lines, catalog)`
- Line: `{ sku, qty, discount% }`. Unknown SKUs land in `skipped[]`
  (never silently dropped — same rule as spec 13 R2); qty and discount
  clamped to ≥ 0 (discount ≤ 100).
- Per line: gross = list × qty; disc = gross × d%; net = gross − disc;
  margin% = (net − cost×qty)/net (0 when net = 0).
- Totals: net, discount, cost, gross, blendedDiscount% (disc/gross),
  blendedMargin% — all 0-safe on empty quotes.

### `approvalFor(blendedDiscount)`
Fixed escalation matrix: ≤5 auto-approved · ≤15 sales manager ·
≤25 VP sales · else CFO+CEO. Boundary values belong to the lower tier.

## Design — `revrec.js`

### `buildSchedule(contract, months = contract.term)`
Obligation kinds:
- `ratable`: amount/(end−start) per month over [start, end).
- `point-in-time`: full amount in month `start`.
- `milestone`: three equal tranches at floor(start + i·(end−start)/3).
Output: monthly rows per obligation + `monthlyTotals`, `cumulative`,
`recognized`, `deferred = tcv − recognized`.

### Guarantees
- Conservation: each obligation's scheduled sum equals its amount
  (within fp tolerance) when its window fits the horizon.
- `deferred ≥ 0` for well-formed contracts (Σ obligations ≤ tcv).
- Truncated horizon: months beyond the horizon are not recognized —
  deferred reflects the remainder.

## Design — `metering.js`

### `meterBill(meter)` / `invoice(baseFee, meters)`
- Utilization = used/included; overage applies only when used > included:
  `round(cost × (used − included)/included × 0.4)` (40% overage premium
  on the pro-rata share — matches the shipped pricing model).
- Invoice: `{ base, usage, overage, total = base + usage + overage }`.
  (R1 correction: the inline component computed overage but omitted it
  from the total — spec makes the invoice include it; the meter table
  already billed usage, overage is the premium on top.)
- Pace projection: `projectedTotal(invoice, dayOfMonth, daysInMonth)`
  linear on usage-driven parts, base fee flat.

## Test plan
- cpq: totals & blended math on a fixture; zero-net margin; unknown-SKU
  skip; clamps; approval matrix boundaries at 5/15/25.
- revrec: per-kind conservation; milestone placement; truncated horizon
  leaves deferred; cumulative is monotone; deferred non-negative.
- metering: no overage at/below included; overage formula exact;
  invoice total includes overage; projection at mid-month.

## Review record — R1
- ✅ Overage-not-in-total flagged as a real defect in the merged
  component and corrected here (spec first, then test, then code).
- ✅ Remaining merged modules audited: PersonalizationDash,
  RevenueDashboard, OrderBook, MarketplaceCommission, UpsellEngine,
  CustomerHealth, SupportSLA are presentation-dominant; queued in
  spec 13 for extraction only if their math grows.
  **[Superseded by spec 16 R1: the CustomerHealth/SupportSLA half of
  this call was wrong — both carry real untested algorithms (health
  score, churn model, SLA breach). Extracted in spec 16. The other five
  remain presentation-dominant.]**
- Verdict: **approved**.
