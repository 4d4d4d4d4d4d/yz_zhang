# Spec 02 — Ad Marketing: Budget Allocation & Pacing

Status: **Approved** · Review: R1 (2026-07-02) · Domain: `logic/marketing.js`

## Problem

Cross-border campaigns split one budget across channels/markets with
different ROAS and hard min/max commitments. Manual splits leak spend;
the engine must allocate toward marginal return under constraints, and
pace daily spend so budgets survive the whole flight.

## Design

### `allocateBudget(total, channels)`
- `channels[]`: `{ id, roas, min = 0, max = ∞ }`.
- Algorithm:
  1. Grant every channel its `min` (if Σmin > total → throw, caller error).
  2. Distribute the remainder **proportionally to ROAS** among channels
     below their `max`, water-filling: when a channel hits `max`, freeze it
     and redistribute the residue among the rest; iterate until stable.
  3. Rounding to cents with largest-remainder so Σ allocations ≡ total.
- Output: `{ allocations: {id: amount}, expectedReturn }`.

### `pacingStatus(budget, spent, elapsedDays, totalDays)`
- Linear pace target with ±10% tolerance band →
  `{ target, delta, status: 'under' | 'on-track' | 'over', dailyRunRate,
  projectedTotal }`. Guards division by zero (day 0 → on-track, target 0).

## Guarantees
- Conservation: allocations always sum exactly to `total` (cent-exact).
- Respect bounds: min ≤ allocation ≤ max for every channel.
- Monotonic: raising a channel's ROAS never lowers its allocation.

## Test plan
- Conservation under awkward totals (e.g. 1000.01 across 3 channels).
- Max-cap water-fill: capped channel's residue flows to others.
- Σmin > total throws a descriptive error.
- Pacing: under/on-track/over classification at band edges; day-0 safe.

## Review record — R1
- ✅ Water-filling preferred over one-shot proportional (respects caps).
- ✅ Largest-remainder rounding added after review caught 1¢ drift.
- Verdict: **approved**.
