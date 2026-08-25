# Spec 52 — Risk Appetite & Control Effectiveness

**Status:** Accepted · **Depends on:** 05 (risk/legal), trust surface

## 1. Problem (critical analysis)

`RiskHeatmap` computed a correct likelihood × impact matrix — but a matrix is
only half of what a GRC surface owes a board. Two ISO 31000 staples were
absent:

- **Risk appetite.** No stated tolerance and no way to see which residual
  risks breach it. "Which risks are above appetite?" is the question a risk
  committee actually opens with, and the screen could not answer it.
- **Control effectiveness.** The inherent → residual delta was shown as a raw
  number ("−10"), never as the fraction of risk the controls actually bought.

It also carried a genuine methodological defect: the "avg reduction" figure
averaged **per-risk percentages**, so a trivial risk fully mitigated counts the
same as a critical one left untouched.

## 2. Scope

- `logic/risk.js` — pure: `riskScore` (clamped to the 0..5 scale),
  `severityBand`, `controlEffectiveness` (null when there is no inherent risk
  to reduce; never negative), `exceedsAppetite` (strictly above; equal is
  within tolerance), `auditRisks` (residual > inherent — controls cannot raise
  risk), `assessRisk`, and `portfolioRisk` with **exposure-weighted**
  `portfolioEffectiveness` alongside the plain `avgEffectiveness`.
- `RiskHeatmap.vue` — scoring/banding now come from the engine; a new **risk
  appetite** panel shows total exposure, portfolio effectiveness, an adjustable
  appetite threshold, and clickable chips for every breaching risk; the detail
  panel gains per-risk control effectiveness and an in/out-of-appetite verdict.

## 3. Review record

**R1 — weight by exposure, and keep both numbers.** The engine returns the
exposure-weighted reduction *and* the plain average, because the two answer
different questions; the UI shows the weighted one and says so on screen. A
test pins the pathological case: a trivial risk mitigated 1 → 0 beside a
critical one stuck at 25 → 25 gives a 50% plain average but a 4% weighted
truth.

**R2 — equal to appetite is within tolerance.** `exceedsAppetite` is strictly
greater-than, matching how a stated threshold reads ("residual must not exceed
8"). A test pins the boundary.

**R3 — surface bad register data, don't clamp it away.** `controlEffectiveness`
floors at 0 so no readout shows negative mitigation, but `auditRisks`
separately reports any entry whose residual exceeds its inherent, so the data
error stays visible rather than being silently normalised.

## 4. Tests
`tests/risk.test.js` (17): score clamping and junk guards, every severity band
boundary, effectiveness including the null and never-negative cases, the
appetite boundary, `assessRisk` on a real and a malformed entry, the hygiene
audit, and portfolio totals, custom appetites, empty-register guards, and the
weighted-vs-average trap.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget, plus a browser smoke: exposure 117 → 46 with 61% portfolio
effectiveness, one breach at appetite 8 (R-001, residual 10), six at appetite
3, none at 25, and R-001's detail reading "50% control effectiveness ·
above appetite, escalate".
