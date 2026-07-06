# Spec 17 — Marketplace Commission Engine (+ queue close-out)

Status: **Approved** · Review: R1 (2026-07-04) · Domain: `logic/commission.js`

## Problem

`MarketplaceCommission` computes real money — tier commission and a
blended rate — inline and untested. It also has a **latent correctness
gap**: each tier shows a commission `cap` ($500k / $200k / $50k), but the
commission math (`gmv × rate`) never applies it. The cap column is
decorative. This is the last extraction that clears spec 13's queue.

## Design — `logic/commission.js`

### `parseCap(cap)`
`'∞'`/`null`/`undefined` → `Infinity`; `'$500k'` → 500000; `'$1.2m'` →
1200000; plain numbers pass through. Unparseable → `Infinity` (fail-open
to "no cap" is safe for a ceiling; documented, not silent).

### The cap is **per-partner**, not per-tier (R1 correction)
A first draft applied the cap in `tierCommission`, but a tier's `gmv` is
the **aggregate** of many partners — capping the aggregate at a
per-partner ceiling ($500k on Gold's $1.24M) understates commission
badly. The blended-rate test caught it. Corrected model:

### `tierCommission(gmv, ratePct)` — aggregate, **uncapped**
`round(gmv × ratePct/100)`. Aggregate GMV is not one partner, and the
tier data carries no per-partner breakdown, so the honest tier figure
applies no cap. Matches the original inline behavior exactly.

### `capCommission(gmv, ratePct, cap)` — **per-partner**, capped
`round(min(gmv, parseCap(cap)) × ratePct/100)`. This is where the cap
lives.

### `blendedRate(tiers)`
`Σ tierCommission / Σgmv × 100`, 2 dp, 0-safe. Uncapped aggregates.

### `earnerCommission(earner, tiers)` / `commissionRun(tiers, earners)`
- Per earner: look up its tier's rate & cap, compute `capCommission`,
  flag `capped: true` when `gmv > cap`. For the shipped fixture every
  earner is under its cap, so no displayed number changes — the value is
  a correctly-capped over-cap earner.
- Run rollup: `{ byTier[], totalGMV, totalCommission, totalPartners,
  blendedRate, earners[] }` — one source of truth for the dashboard.

## Guarantees
- Pure, deterministic, total (unknown tier → 0 commission, flagged).
- Commission ≤ cap × rate for every earner; ≤ gmv × rate always.
- Conservation: run's `totalCommission` = Σ tier commissions.

## Test plan
- parseCap: ∞/k/m/number/garbage.
- tierCommission: under cap = gmv×rate; over cap = cap×rate; at cap exact.
- blendedRate: fixture value; empty → 0.
- earnerCommission: fixture earners match `gmv×rate` (all under cap);
  a synthetic over-cap earner is capped and flagged.
- run: totals conserve; unknown tier → 0 + flag.

## Migration queue — CLOSED

Audit of the final watchlist (spec 16 left five):

| Module | Verdict | Evidence |
|---|---|---|
| `MarketplaceCommission` | **extracted** (this spec) | real commission math + cap gap |
| `UpsellEngine` | presentation | `score`/`upside` are hardcoded data fields; only filter/find/reduce |
| `RevenueDashboard` | presentation | waterfall = chart geometry over hardcoded deltas |
| `OrderBook` | presentation | filter + reduce over hardcoded orders |
| `PersonalizationDash` | presentation | reduce + sparkline array generation |

No console module carries an unextracted algorithm. Spec 13's queue is
empty and **closed**; future components must use the logic layer from day
one (spec 00 rule), so the queue should not re-open except on external
merges (as happened at v9/v11).

## Review record — R1
- ✅ Cap enforcement is a reviewed behavior change with zero fixture
  impact (safe) but real correctness value (over-cap partners).
- ✅ Queue closure backed by a per-module audit table, not assertion —
  the same rigor that caught the spec-16 miscall.
- Verdict: **approved**.
