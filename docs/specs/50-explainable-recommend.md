# Spec 50 — Wire the Flagship Recommender to Its Own Engine

**Status:** Accepted · **Depends on:** 01 (recommendation core)

## 1. Problem (critical analysis)

An audit for logic modules with **no consumer anywhere in `src/`** found three:
`bundleBudget` (legitimately consumed by `scripts/check-bundle.mjs`), and two
genuinely orphaned engines — `marketing.js` and **`recommend.js`**.

`recommend.js` is the platform's first and headline capability: the console
section is titled *"AI Recommendations — **Explainable**, ranked ad concepts"*.
It has weighted multi-signal scoring, per-signal contribution explanations, and
an MMR-lite diversity re-rank. It was fully tested and **shipped to nobody**.

`RecommendDeep.vue` instead ranked by an unweighted mean of four decorative
scores, with a `+4` tilt for brand voice. Consequences:

- **No explanations at all**, on the surface that sells explainability.
- **No diversity re-rank** — one format could sweep the top-N.
- Worst: `goal`, `audience`, and `budget` were **decorative inputs**. The
  operator could switch ROAS→Reach, change audiences, or move the budget
  slider and the output would not change by a single position.

## 2. Scope

- `logic/recommend.js` — adds `conceptSignals(concept, ctx)` and `GOAL_METRIC`:
  maps a concept plus the operator's brief onto the 0..1 signal vector the
  scorer already consumes. `goal` selects which metric drives `performance`
  (roas / cvr / ctr, each with its own normalising cap); `audience` drives
  `affinity` as the share of requested audiences the concept targets; `voice`
  drives `brandFit`; and a budget that cannot fund a concept discounts the
  performance it could realistically deliver.
- `RecommendDeep.vue` — consumes `conceptSignals` + `rankCandidates`; the
  catalog gains the targeting facts (`audiences`, `voice`, `minBudget`); the
  decorative score bars are replaced by the **real per-signal contributions**
  (value × weight → points), and a badge marks concepts demoted by the
  diversity re-rank.

## 3. Review record

**R1 — neutral, not zero, when unspecified.** With no audience selected,
`affinity` is 0.5. Scoring it 0 would let an empty filter silently suppress
every concept, which reads as a broken ranker rather than an unfiltered one.

**R2 — budget gates performance, and says so.** Rather than a separate
"budget fit" signal nobody would interpret, an unfundable concept's
`performance` is scaled by the fundable fraction. The doc comment states the
reasoning so the number is auditable.

**R3 — replace the decorative bars, don't add beside them.** Keeping the old
relevance/creativity/fit/risk bars next to real contributions would leave two
competing explanations on screen. The honest move is to show only the one that
actually produced the ranking.

**R4 — `marketing.js` remains orphaned.** Recorded here rather than quietly
left: `allocateBudget`/`pacingStatus` still have no consumer. Wiring them into
`MarketingControl.vue` is the natural next batch; this spec does not claim it.

## 4. Tests
`tests/conceptSignals.test.js` (13): goal→metric selection producing three
distinct values, unknown-goal fallback, affinity as an overlap share, the
neutral-when-empty rule, exact voice match, budget discounting (half budget →
half performance; zero → zero), no penalty without a budget floor, all signals
clamped to [0,1], empty-input guard — plus **end-to-end proof the brief changes
the ranking**: the high-ROAS demo wins under `goal: roas`, the high-CTR reel
wins under `goal: reach`, and explanations come back ordered by contribution.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget, plus a browser smoke: switching the goal from ROAS to Reach
reorders the results (the 5.2% CTR diary overtakes the founder POV), and each
card shows its contributions — top signal "Audience affinity 28.0 pts".
