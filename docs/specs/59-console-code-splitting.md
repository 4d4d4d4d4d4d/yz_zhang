# Spec 59 — Console Code-Splitting, and a Budget That Measures a Reader

**Status:** Accepted · **Depends on:** 20 (section registry), 28 (bundle budget), 56 (a11y sweep), 58 (locale splitting)

## 1. Problem (critical analysis)

**(a) The console shipped all seven sections to anyone who opened one.**
`Console.vue` imported all 51 panel components eagerly, producing a 332 KB /
109.34 KB gzip chunk against a 110 KB budget — **0.6% of headroom**, with 68
components still queued for i18n migration. A reader opening *Deals* paid for
Recommendations, Marketing, Partners, Showcase, Immersive and Trust as well.

**(b) The "total bytes" budget had quietly stopped meaning anything.**
When the app shipped in two chunks, "sum of all chunks" was a fair proxy for
what a visitor downloads. Splitting breaks that equivalence — and breaks it in
the direction that punishes the right decision. Measured here: splitting the
console raised the total from 230.7 to 240.4 KB (lost cross-chunk compression)
while cutting what a reader downloads to open a console section from **191.4 KB
to 106.9 KB, a 44% reduction**. A guard watching only the sum would have scored
that as a regression and pushed the codebase back toward one big chunk.

**(c) The a11y sweep would have gone vacuous, silently.** This is the finding I
did not expect. Spec 56's sweep clicks all 51 sub-tabs and asserts that no
control is unlabeled. With async panels it scanned **zero** controls after each
click — the panel had not resolved — and reported a clean bill of health. A
guard that stops guarding while still passing is worse than no guard, because
its green tick is now evidence of nothing.

## 2. Scope

**Split by section, not by panel.** `src/console/sections/{recommend,marketing,
partners,deals,showcase,immersive,trust}.js` — one barrel per section, mapping
sub-tab key → component. Vite emits one chunk each (8.4–20.7 KB gzip).

**`src/console/panels.js`** — `loadSection` (cached, de-duplicated, evicts a
failed load so a retry can succeed), `isSectionLoaded`, `prefetchSection`
(failure-tolerant).

**`src/views/Console.vue`** — each panel is a `defineAsyncComponent` over its
section's chunk, with a 180 ms delay before `PanelSkeleton` so a fast chunk
never flashes a placeholder. The 56 eager imports and the `COMPONENTS` map are
gone. The panel is wrapped in `.panel[data-panel]` — a stable hook for tests.

**`src/logic/prefetch.js`** — `prefetchOrder(allKeys, activeKey, recents, {max})`
and `idleSchedule`/`requestIdle` with the globals injected.

**`src/logic/bundleBudget.js`** — `PATHS` + `pathCost`: what one reader
downloads for one surface. `Console` budget drops 110 → 20 (shell only), every
section gets the same `SECTION_BUDGET = 22` so none can outgrow its peers, and
`TOTAL_BUDGET` is demoted to a coarse anti-bloat ceiling.

**`src/components/PanelSkeleton.vue`** — `role="status" aria-busy="true"` with
a localized label, and no sheen under `prefers-reduced-motion`.

## 3. Review record

**R1 — section granularity, not per-panel.** Per-panel splitting would have
produced 51 chunks and turned every sub-tab flick into a network round trip.
The section is the unit people actually navigate: pick a module from the
sidebar, then flick between its sub-tabs. Browser-verified — opening
`/console/deals` fetches `deals`, and four consecutive sub-tab clicks fetch
**nothing**.

**R2 — prefetching everything is the same mistake, one hop later.** It spends
the reader's bandwidth on six sections to save a click on one. The policy is
capped at two and evidence-led: most-recently-visited sections first (console
work is back-and-forth between two or three modules, not a linear tour), then
the sidebar neighbours. Browser-verified: `/console/deals` warms `showcase` and
`partners`; navigating to Trust warms `immersive`.

**R3 — the vacuity was caught by a sentinel I added defensively, and it fired
on the first run.** The a11y sweep reported 0 buttons and 0 controls. Had I
awaited the panels without also counting what was scanned, the suite would have
gone green and spec 56's guarantee would have evaporated with no signal at all.
The floors (700 buttons, 80 controls, 51 sub-tabs) are calibrated against the
totals measured on the synchronous build (757 / 86 / 51) — verified by stashing
the async change and re-measuring, not by guessing. The same sentinel is now in
`mount.smoke`: "no errors were thrown" is not a claim you can make about a
panel that never mounted.

**R4 — the budget had to be fixed, not relaxed.** The tempting move was to
raise `TOTAL_BUDGET` past 240. That would have kept a metric nobody downloads
as the thing CI defends. `pathCost` charges the includes plus the **single
heaviest** alternative, because a reader opens one section — and a test pins
exactly this: a split that raises the total while cutting delivered bytes must
not register as a violation.

**R5 — the failure message names the section.** `(path: console via marketing)`
rather than `(path: console)`. A budget failure whose message does not say what
to look at costs an investigation every time it fires.

**R6 — unreachable panels are the orphan problem again.** A component sitting
in a section barrel with no matching sub-tab is dead weight the reader
downloads and can never see. `tests/consolePanels.test.js` asserts the barrel
and the registry agree in *both* directions — same discipline spec 55 applied
to the logic layer. Teeth-verified with a stray `ghost` entry.

**R7 — a failed chunk is evicted, not cached.** Caching the rejected promise
would leave a section permanently broken for the rest of the session over one
dropped request. `ModuleBoundary` (spec 27) still catches the failure and
offers Retry — which now actually retries.

**R8 — the skeleton is an `aria-busy` status region.** A bare spinner leaves a
screen reader silently on an empty card. The 180 ms delay means most switches
never render it at all.

## 4. Results

| | before | after |
|---|---:|---:|
| `Console` chunk (gzip) | 109.34 KB | **5.92 KB** |
| delivered to open a console section | 191.4 KB | **106.9 KB** (−44%) |
| sum of all chunks | 230.7 KB | 240.4 KB |
| landing page delivered | — | 83.1 KB |

Section chunks: showcase 8.37, immersive 12.28, partners 16.05, deals 16.58,
trust 16.63, recommend 17.60, marketing 20.74 KB gzip — all under the 22 KB
per-section ceiling.

## 5. Tests

- `tests/consolePanels.test.js` (new, 15 cases) — loaders match the registry;
  every sub-tab resolves to a component *and* no barrel ships an unreachable
  one; promise caching; unknown section rejects; prefetch never throws;
  prefetch order (MRU → neighbours), cap, de-duplication, junk history, unknown
  active key; idle scheduling across all three runtime shapes.
- `tests/bundleBudget.test.js` — +7 cases for `pathCost` and the per-section
  ceiling, including the explicit "higher total, lower delivered bytes is not a
  regression" case.
- `tests/a11y.console.test.js`, `tests/mount.smoke.test.js` — await the section
  chunk, refuse to score a skeleton as a rendered panel, and carry the
  anti-vacuity sentinels.

Teeth-verified, each restored immediately: a stray panel in the `showcase`
barrel fails the reachability check; a `loadSection` that resolves to `{}`
fails the a11y sentinel (489 buttons < 700) *and* names every missing panel in
`mount.smoke`.

## 6. Gate

`npm run test:coverage` — **813 tests across 63 files**, functions 100%,
statements/lines 99.82%, branches 93.64%; `prefetch.js` and `bundleBudget.js`
both at 100% branch coverage. `npm run build` clean. `npm run check:bundle` —
all chunks and both paths within budget.

Browser-verified at `/console/deals` → sub-tab flicks → `/console/trust`: the
right chunk arrives on section entry, neighbours are warmed speculatively,
sub-tab switches inside a section cost no network, and the console reports no
errors.
