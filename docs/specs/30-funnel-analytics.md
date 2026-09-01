# Spec 30 — Funnel Analytics: Closing the Write-Only Recorder Loop

Status: **Approved** · Review: R1 (2026-07-07)
Domains: `logic/funnel.js` · `components/FunnelView.vue`
(new `marketing/funnel` console sub-tab)

## Problem (v25 critical review)

Spec 29 added an analytics recorder — but it is **write-only**. Events
go in (`form_view`, `form_submit`, …) and nothing ever reads them. A
funnel you record but never aggregate is not measurement; it's a landfill.
Every analytics product (GA, Amplitude, Mixpanel, PostHog) closes this
with a funnel view: per-stage counts, the conversion rate between
consecutive stages, overall conversion, and — most actionable — the
biggest drop-off, so an operator knows *where* the funnel leaks.

## Design — `logic/funnel.js`

### `analyzeFunnel(events, stages)`
- `events`: `[{ name, ... }]` (the recorder's shape). `stages`: an
  ordered list of event names defining the funnel, e.g.
  `['page_view', 'form_view', 'form_submit', 'form_success']`.
- Returns `{ steps, overall, biggestDrop }`:
  - `steps[i]`: `{ stage, count, rate }` where `rate` is the fraction
    retained from the **previous** stage (step 0 → rate 1). Division by a
    zero upstream count yields rate 0, never NaN.
  - `overall`: last-stage count / first-stage count (0 when the funnel
    never started).
  - `biggestDrop`: the step with the lowest step-rate among steps ≥ 1
    (the leak to fix first), or `null` for a ≤1-stage funnel.
- Events whose name isn't a funnel stage are ignored; counts are by name
  occurrence (a stage repeated in the stream sums — matches how the
  recorder logs retries).

### Guarantees
- Pure, total, deterministic. Empty events → all-zero steps, overall 0,
  biggestDrop null. Monotonic-agnostic: real funnels can have a later
  stage exceed an earlier one (multi-submit); rates are reported as-is,
  clamped to [0, ∞) but never negative or NaN.

## Design — `FunnelView.vue`
- New `marketing/funnel` sub-tab. Renders a horizontal funnel bar per
  stage (width ∝ count), the step conversion %, overall conversion, and
  a highlighted biggest-drop callout.
- Data: a realistic **seeded demo baseline** funnel (the console operator
  hasn't necessarily visited the Contact form), **merged** with any live
  events from the shared recorder — so a real submit this session bumps
  the numbers. Merge is additive on stage counts; the seed makes the
  dashboard meaningful on first load.
- Copy in `funnel.*` and the `console.tabs.marketing.funnel` label ×4.

## Extension path exercises the guards
Adding the sub-tab goes through the single-source `SECTIONS` registry
(spec 20) — so the i18n shell-coverage test (spec 14) auto-requires the
new label across all locales, and the mount smoke (spec 21) auto-covers
the new component. No guard is opted out of.

## Test plan
- analyzeFunnel: a 4-stage fixture with known counts → exact step rates,
  overall, and biggestDrop identifies the worst step; empty → zeros/null;
  div-by-zero upstream → rate 0 not NaN; non-stage events ignored;
  single-stage funnel → biggestDrop null.
- Browser: the funnel sub-tab renders 4 stages with descending bars, the
  biggest-drop callout names a stage, and firing a form_submit via the
  live recorder increments the matching stage.

## Review record — R1
- ✅ Rates clamped to avoid NaN but not forced monotonic — a real funnel
  where re-submits exceed views is data, not an error to hide.
- ✅ Seed + live merge so the dashboard is meaningful cold but still
  reflects this session; live-only was rejected (blank on first load).
- Verdict: **approved**.
