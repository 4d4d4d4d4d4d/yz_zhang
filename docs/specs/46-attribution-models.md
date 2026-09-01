# Spec 46 — Multi-Touch Attribution (computed, not tabulated)

**Status:** Accepted · **Depends on:** marketing surface (spec 02 lineage)

## 1. Problem (critical analysis)

`AttributionWaterfall` offered seven attribution "models" — but the credit
splits were a **hardcoded lookup table** (`splits = { last: [12,18,...], ... }`).
Nothing was computed from customer journeys: switching model just swapped one
literal array for another. Attribution *is* the product in this surface (GA4,
Adobe, Rockerbox), so a table of magic numbers is the whole feature missing.
The "top 3 paths" and the "delta vs last-touch" panels were likewise static and
could not agree with the bars by construction.

## 2. Scope

- `logic/attribution.js` — pure, journey-driven credit:
  - Journeys are `{ touches: [{channel, at}], convertedAt, count }`, where
    `count` is standard path rollup.
  - Rule-based per-journey credit: **first**, **last**, **linear**,
    **decay** (exponential, configurable half-life), **position** (40/20/40,
    degrading correctly at n=1 and n=2).
  - **Shapley** over channel coalitions: characteristic function
    `v(S) = converting weight of journeys whose channel set ⊆ S`, exact
    Shapley value via the factorial weighting (6 channels → 64 subsets).
  - `attribute()` normalizes to fractions summing to 1; `attributionRows()`
    ranks channels descending with percentages.
- `AttributionWaterfall.vue` — one aggregated path dataset now feeds **all
  three** panels: the credit bars, the top-3 paths, and the delta-vs-last-touch
  chart (computed as `model − last`), so they can never disagree.

## 3. Review record

**R1 — dropped "Data-driven".** The old table listed a `datadriven` model
described as "learned credit via counterfactual lift modeling." That requires a
trained model; faking it with a literal array is exactly the problem this spec
fixes. It was removed rather than simulated — the six shipped models are all
genuinely computed.

**R2 — Shapley is exact, not sampled.** With a bounded channel set the full
2^n coalition sum is cheap and deterministic, so no Monte-Carlo approximation
(and no RNG) is needed. Tests assert the axioms directly: efficiency
(credit sums to 1) and symmetry (interchangeable channels split evenly).

**R3 — one dataset, three panels.** Prior rounds' lesson (spec 30/40): a
producer without a consumer, or two consumers with separate data, drifts. The
paths panel and delta panel derive from the same `PATHS` rollup as the bars.

**R4 — never NaN.** Unknown model falls back to linear; zero-span decay
journeys fall back to even credit; empty/invalid journeys return `{}`.

## 4. Tests
`tests/attribution.test.js` (17): first/last/linear exactness, decay half-life
arithmetic, position 40/20/40 plus n=1 and n=2 degradation, Shapley efficiency +
symmetry + a solo-converting channel outranking a tag-along, path-count
weighting, normalization across every model, unknown-model fallback,
missing-`convertedAt` decay, and the empty/invalid guards.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke across models: last-touch gives TikTok 0% (it never
closes) and Direct 77%; first-touch gives Direct 0% (it never starts) and
TikTok 61%; every model totals 100%.
