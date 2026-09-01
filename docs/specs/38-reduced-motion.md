# Spec 38 — Reduced Motion (respect OS + user toggle)

**Status:** Accepted · **Depends on:** 27 (store), 28/31 (a11y)

## 1. Problem (critical analysis)

The app is motion-heavy — a canvas orb loop in the hero, live-updating feeds,
route/hover transitions — and **ignores `prefers-reduced-motion` entirely**.
That fails WCAG 2.3.3 and is a real problem for users with vestibular
sensitivity. Industry leaders go one step further than the OS setting and offer
an **in-app motion toggle** (GitHub, Slack), which also lets a user opt out on a
shared machine whose OS they can't change.

## 2. Scope

- `logic/motion.js` — pure `resolveMotion(osReduce, userPref)` (user choice
  overrides the OS) and `nextMotionPref` for a single cycling control.
- `store/workspace.js` — persist `motion` ∈ {system, reduce, full}.
- `composables/useReducedMotion.js` — reactive: live `matchMedia` + the stored
  pref, reflected onto `<html data-reduce-motion>` so CSS honors a user override
  even when the OS disagrees. matchMedia/document guarded for test/SSR safety.
- `styles/global.css` — the standard "nuke": near-instant animation/transition
  durations under both `@media (prefers-reduced-motion: reduce)` and
  `:root[data-reduce-motion="true"]`.
- `VideoHero.vue` — the flagship JS loop: renders a single still frame and
  stops scheduling `requestAnimationFrame` when reduced; restarts if the viewer
  re-enables motion.
- `MotionToggle.vue` in the navbar — cycles system → reduced → full, localized
  across all four locales.

## 3. Review record

**R1 — user pref overrides OS.** `resolveMotion` returns true/false for
reduce/full regardless of the media query; only `system` follows the OS. The
`data-reduce-motion` attribute carries that override into CSS, which a media
query alone cannot express.

**R2 — CSS nuke + explicit JS gating.** The global media query stops *CSS*
animation/transition, but `requestAnimationFrame` canvas loops are invisible to
CSS. The hero loop is gated explicitly; the remaining console-internal canvas
loops (SecurityRibbon, WorkerSwarm, …) follow in a staged rollout (per spec 13
precedent) — the hero is the landing-page motion that matters most.

**R3 — no new deps, test/SSR-safe.** matchMedia and document are feature-detected
so mount-smoke (happy-dom) and any SSR path never throw.

## 4. Tests
`tests/motion.test.js`: `resolveMotion` across every OS × pref combination
(incl. unknown/omitted), boolean coercion, and the `nextMotionPref` cycle.
Store persistence covered by `tests/workspace.test.js`; the gated hero and the
toggle by the mount-smoke sweep; i18n parity by `tests/i18n.test.js`.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke under emulated `reduce`: `<html>` gains
`data-reduce-motion="true"` and the navbar toggle cycles the label.
