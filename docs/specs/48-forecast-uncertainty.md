# Spec 48 — Forecast Prediction Intervals

**Status:** Accepted · **Depends on:** 13 R4 (forecast engine)

## 1. Problem (critical analysis)

`logic/forecast.js` is genuinely good work — saturating response curves,
marginal ROAS, λ-sweep water-fill allocation. But it emits a **single point
estimate**: "projected revenue $542k", full stop. Every serious forecasting
product (Prophet, Amazon Forecast, Anaplan) ships a prediction interval,
because a naked point forecast invites overconfidence in a number that is a
model output, not a measurement. Budget decisions were being framed as
certainties.

## 2. Scope

Extends `logic/forecast.js` (same domain, so no new module):

- `Z_SCORES` — p80 / p90 / p95.
- `portfolioSd(revenues, { cv, correlation })` — revenue is **linear in each
  channel's response coefficient `k`**, so a relative uncertainty on `k` passes
  straight through to revenue. Portfolio spread is the full covariance sum:
  independent channels diversify (√ of summed variances), perfectly correlated
  ones don't (variances add linearly). Correlation is clamped to [0,1].
- `forecastBand(mean, sd, level)` — interval clamped at 0 (revenue can't be
  negative), unknown level falls back to p80.
- `projectWithUncertainty(channels, budget, opts)` — the existing projection
  plus `sd`, `relativeCv`, and `band`.

`ForecastSim.vue` gains a **prediction interval** panel: the band, a p80/p90/p95
selector, and an explicit statement of the assumptions (20% response-curve
uncertainty, 0.3 channel correlation) plus the resulting portfolio CV.

## 3. Review record

**R1 — model uncertainty, not measurement noise.** The CV is stated as
uncertainty on the *response coefficient*, which is what it actually is. The
UI names the assumption on screen rather than presenting the band as if it were
empirically derived — an honest interval beats a confident-looking one.

**R2 — correlation is a first-class input.** Assuming independence would
understate risk: marketing channels share seasonality and macro demand. The
default is 0.3, and the covariance form makes the assumption explicit and
tunable rather than hidden in a √n.

**R3 — clamp the low edge, not the high one.** Revenue has a hard floor at 0
but no ceiling, so the interval is asymmetric at the bottom only. Clamping both
would silently narrow the stated risk.

## 4. Tests
`tests/forecastUncertainty.test.js` (12): single-channel identity (correlation
irrelevant), the **diversification property** (4 equal independent channels →
2× the spread of one, not 4×), the perfectly-correlated bound (spread = cv ×
total), partial correlation strictly between those bounds, correlation
clamping, level widening (p95 > p80), the zero-edge clamp, collapse to a point
at sd 0, unknown-level fallback, and portfolio CV strictly below per-channel CV.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: P80 $446k–$639k around $542k, P95 widening to
$394k–$691k, portfolio CV 13.9% against a 20% per-channel input.
