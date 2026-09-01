# Spec 21 — Automated Component Mount-Smoke in CI

Status: **Approved** · Review: R1 (2026-07-04)
Artifacts: `tests/mount.smoke.test.js`, `vite.config.js` (test env)

## Problem

Six real bugs were found across the iteration; **two were component
mount/render crashes** — the Contact page's unescaped-`@` i18n crash and
CustomerHealth's dangling `band()`/`weights` template bindings after the
spec-16 extraction. Both were caught only because a human ran an ad-hoc
Playwright smoke by hand. Nothing in the committed suite or CI mounts the
components; a render-time crash ships green today unless someone
remembers to smoke it.

The logic layer is exhaustively guarded (unit + integration + coverage),
but the **view layer has no automated guard at all**. That asymmetry is
the gap.

## Design — `tests/mount.smoke.test.js`

Mount every real component under `happy-dom` with the **real** plugins,
asserting no throw and no Vue warning:

- **i18n**: the actual `createI18n` built from the shipped locale
  catalogs — so an i18n compile crash (the `@` bug) reproduces here.
- **router**: a memory router carrying the real routes — so
  `<router-link>` and `useRoute` resolve.
- **Coverage of the surface**: iterate the single-source `SECTIONS`
  registry (spec 20) and mount each section's component set via a
  `section/sub → component` map; plus each marketing view (Home, Product,
  Studio, Cases, Pricing, About, Contact). Registry-driven, so a new
  section is smoked automatically.
- **Assertion**: mounting throws → fail with the component name; any
  `console.error`/Vue warn during mount → fail. Components with timers
  (`setInterval`) are unmounted immediately to avoid open handles.

### Test env
`vite.config.js` `test.environment = 'happy-dom'`. Logic tests are
environment-agnostic and unaffected; only the DOM-mounting file needs it.

## Test plan
- Every console section component and marketing view mounts clean.
- Verified during development (teeth): reintroducing an unescaped `@` in a
  locale, or a dangling template binding, fails the smoke with the
  offending component named.

## Review record — R1
- ✅ jsdom/happy-dom mount over a full Playwright e2e in CI: no browser
  download, runs in the existing vitest job, and catches the crash class
  that actually bit us (render/mount errors). Interactive-flow depth
  stays with the manual Playwright pass when needed.
- ✅ Registry-driven component list so the smoke can't silently miss a new
  section (consistent with spec 20).
- Verdict: **approved**.
