# Spec 18 — Logic-Layer Coverage Gate

Status: **Approved** · Review: R1 (2026-07-04)
Artifacts: `vite.config.js` (coverage config), `.github/workflows/ci.yml`

## Problem

Spec 12 made "every logic module has tests" a written policy, and spec
13's migrations honored it — but nothing *enforces* it. A new
`src/logic/*.js` shipped without a test passes CI today. The invariant is
manual; this spec makes it executable, the same move spec 14 made for
i18n completeness.

Measured baseline (this spec's audit): the logic layer is at **100 %
function, 99.6 % statement/line, ~89 % branch** coverage — already
complete, just ungated.

## Design

### Coverage config (`vite.config.js`)
`test.coverage` via `@vitest/coverage-v8`:
- `include: ['src/logic/**']` — the unit-tested surface. Vue components
  and views are presentation (driven by browser smoke, not units);
  including them would measure the wrong thing and force meaningless
  component unit tests.
- `thresholds` (global): **functions 100**, statements 95, lines 95,
  branches 85.
  - `functions: 100` is the load-bearing gate — an untested exported
    function drops it below 100 and fails CI. This is the executable form
    of "every algorithm is tested."
  - statements/lines 95 and branches 85 sit just below the measured
    baseline: tight enough that a whole untested module fails them,
    loose enough to absorb a defensive guard line without flaking.

### Scripts & CI
- `package.json`: `"test:coverage": "vitest run --coverage"`.
- CI runs `npm run test:coverage` (tests + threshold) then `npm run
  build`. `npm test` stays as the fast, un-instrumented local loop.

### Accompanying test-maintenance
Branch coverage on `commission.js` (74 %) and `interpreter.js` (77 %) is
the weakest — mostly fail-safe guards. Top up with targeted branch tests
so the 85 % floor has margin and the guards are actually exercised, not
just present.

## Test plan
- `npm run test:coverage` passes with the configured thresholds on the
  current tree.
- Verified during development: deleting a logic test (dropping a module's
  function coverage) fails the gate — the gate has teeth.

## Review record — R1
- ✅ Scope coverage to `src/logic/**`, not the whole app — components are
  smoke-tested by design; a global threshold would be a lie or a
  busywork generator.
- ✅ `functions: 100` chosen as the primary invariant over a high line %
  — it maps most directly to "no untested algorithm."
- Verdict: **approved**.
