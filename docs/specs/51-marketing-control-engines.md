# Spec 51 — Marketing Control: Three Engines Wired, One Comparator Fixed

**Status:** Accepted · **Depends on:** 02 (marketing core), 35 (sortRows), 45 (significance)

## 1. Problem (critical analysis)

Spec 50 recorded `marketing.js` as the last orphaned engine. This closes it,
and auditing its intended consumer surfaced two more instances of the same
pattern plus a comparator defect.

`MarketingControl.vue` had:

1. **No budget allocation or pacing at all**, while `marketing.js` sat unused
   with a cent-exact largest-remainder water-fill allocator (min/max bounds)
   and a pacing model with tolerance bands.
2. **A hardcoded "AI suggestion"** — `{ Meta: 32, TikTok: 40, Google: 16,
   YouTube: 12 }`. An "AI rebalance" that is a literal object, with copy
   claiming it came from "the last 7-day Pareto frontier".
3. **A hardcoded A/B verdict** — `probability: 96.8, status: 'significant'` —
   even though spec 45 had already shipped a tested two-proportion z-test.
4. **An inconsistent comparator**:
   `(a, b) => a[k] > b[k] ? dir : -dir` never returns 0, so for equal values
   `compare(a,b) === compare(b,a) === dir`. That violates the comparator
   contract and yields implementation-defined ordering.

## 2. Scope

- `logic/marketing.js` — adds `channelRollup(campaigns)`: groups campaigns by
  channel with **spend-weighted** ROAS (revenue ÷ spend), never a mean of
  per-campaign ratios; and `percentShares(amounts)`: whole-percent shares via
  largest remainder.
- `MarketingControl.vue` — consumes `channelRollup` → `allocateBudget` for the
  suggestion (5% floor per channel) and `pacingStatus` for a new pacing panel;
  the A/B verdict now comes from `proportionZTest` + `recommendation`; the
  table sorts through `sortRows`/`nextDir`.

## 3. Review record

**R1 — spend-weighted, not a mean of ratios.** A £10 campaign at 10× next to
£990 at 2× averages to 6.0× as a mean of ratios; the truth is 2.08×. Feeding
the mean into a ROAS-proportional allocator would misdirect real budget, so the
rollup weights by spend and a test pins the trap explicitly.

**R2 — the rounding bug I introduced, then fixed.** The first wiring rounded
each channel's share independently: 36+38+22+5 = **101%**. `applyAI` feeds
those into a reallocator that assumes 100, so the drift would corrupt the
budget. `percentShares` applies largest-remainder so the total is exactly 100,
with a test pinning that specific 101% case.

**R3 — the pacing band edge is inclusive.** Writing the tests, an expectation
of `'over'` at delta exactly equal to the ±10% band failed. The engine was
right — `delta > band` is strict — so the test was corrected and a second test
now documents the boundary as still on-track rather than leaving it implicit.

## 4. Tests
`tests/channelRollup.test.js` (16): grouping and spend sums, the spend-weighted
ROAS trap, zero-spend without NaN, spend ranking, missing-channel and null
guards; rollup→allocator integration (full budget allocated, highest ROAS gets
the largest share, caps respected); pacing over/under/on-track **and the
inclusive band edge**; and `percentShares` totalling exactly 100, staying
within a point of the exact share, exact splits, empty input, and tie
determinism.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget, plus a browser smoke: A/B reads "Keep A — B is significantly
worse" at p 0.002 / z −3.15 (was a hardcoded 96.8%); pacing reads $77,200 of
$100,000 at day 18/30 → **over** by $17,200 against a $60,000 target, run rate
$4,289/day, projected $128,667; allocations total exactly $100,000 with
YouTube at its $5,000 floor; and the AI shares sum to 100.
