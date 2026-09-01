# Spec 45 — A/B Test Statistical Significance

**Status:** Accepted · **Depends on:** experiments surface (spec 06 lineage)

## 1. Problem (critical analysis)

`ExperimentManager` shows experiments with a `pval` column — but those values
are **hardcoded strings** ('0.003', '0.084', …). There was no way to actually
*compute* significance in-tool, which is the one thing an experimentation
platform exists to do (Optimizely, VWO, Statsig). Without it an operator ships
on gut feel and can't tell a real winner from noise.

## 2. Scope

- `logic/significance.js` — pure two-proportion z-test: `normalCdf` (closed-form
  A&S erf approximation, no RNG), `proportionZTest({convA,nA,convB,nB,alpha})`
  → rates, absolute diff, relative lift, z, two-tailed p-value, `significant`
  verdict, and a 95% CI on the difference; `recommendation` → ship /
  keep_testing / rollback / invalid.
- `ExperimentManager.vue` — a **Significance calculator** panel: control vs
  treatment visitors + conversions in, live verdict + lift + p + z + CI out,
  colour-coded ship/keep/rollback.

## 3. Review record

**R1 — closed-form, deterministic.** The normal CDF uses the Abramowitz &
Stegun 7.1.26 erf approximation (|error| < 1.5e-7), so results are exact and
testable against known anchors (Φ(1.96)=0.975) — no simulation, no RNG.

**R2 — pooled SE for the test, unpooled for the CI.** Standard practice: the
z-statistic uses the pooled proportion (null hypothesis of equal rates); the
confidence interval on the difference uses each arm's own variance.

**R3 — fail safe, no NaN.** Zero visitors → `{valid:false}`; zero conversions
in both arms → z=0, p=1, not significant. An experiment readout must never show
`NaN`.

## 4. Tests
`tests/significance.test.js`: CDF anchors, a genuine winner flagged significant
(10%→13% at n=1000), a tiny difference not, p-value shrinking with sample size,
zero-conversion safety, invalid without visitors, and every `recommendation`
branch.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: 2.40% vs 2.96% → "Ship" (p≈0.006); 2.40% vs 2.43%
→ "Keep testing" (p≈0.87).
