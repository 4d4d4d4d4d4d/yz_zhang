# Spec 56 — Console-Wide Accessibility Conformance

**Status:** Accepted · **Depends on:** 21 (mount smoke), 28/31/38 (a11y work)

## 1. Problem (critical analysis)

`tests/a11y.test.js` was 61 lines covering exactly one component
(`CommandPalette`) plus a title helper. Meanwhile the interactive surface grew
to ~50 console components — and the last several specs added *more* controls:
range sliders for risk appetite (52), negotiation settlement (49), budget
allocation (51), and a p80/p90/p95 selector (48).

A sweep across every console sub-tab found **33 form controls with no
accessible name**. A screen reader announces these as "slider, blank" or
"edit text, blank": the operator hears that a control exists but not what it
does. That is WCAG 3.3.2 (Labels or Instructions) and 4.1.2 (Name, Role,
Value).

The a11y work in specs 28/31/38 held up — buttons, tab order and images came
back **clean** — but nothing was guarding the form controls, so each new
slider silently added a violation.

## 2. Scope

- `tests/a11y.console.test.js` — mounts `Console` for every section, clicks
  through **every** sub-tab, and asserts four statically-detectable WCAG
  conditions across the rendered tree:
  - every `<button>` has an accessible name (text, `aria-label`, `title`, or
    `aria-labelledby`);
  - every `input` / `select` / `textarea` has a name or an associated
    `<label>` (wrapping or `for=`);
  - no positive `tabindex` (2.4.3 — it breaks document tab order);
  - every `<img>` has `alt` or is `aria-hidden`.
- **33 violations fixed** across 11 components: sliders in `AIRecommend`,
  `ForecastSim` (×2), `MarketingControl`, `ModelRegistry`, `RecommendDeep`;
  search boxes in `PipelineBoard`, `OrderBook`, `ClauseLibrary`; the
  `AudienceBuilder` rule values; `CPQEditor` quantity/discount fields;
  `AvatarStudio`'s script textarea; `RecommendAdvanced`'s file input; and the
  `NegotiationPlaybook` reply box.

## 3. Review record

**R1 — dynamic controls get dynamic names.** Per-channel and per-line-item
controls are labelled from their own data (`` :aria-label="`${k} budget share
percent`" ``), so four sliders in a row do not all announce "budget". A static
label would have satisfied the guard while leaving the screen-reader
experience ambiguous.

**R2 — the failure message is the fix list.** The assertion reports every
violation grouped by kind with its section, sub-tab index, element and nearby
text. A guard that only says "expected 33 to be 0" would send the next person
back to writing the probe I had to write.

**R3 — statically detectable only, and say so.** This does not replace an
audit: contrast ratios, focus-visible styling and screen-reader flow are out
of scope for a jsdom mount. The spec claims what it checks and no more.

## 4. Tests
The guard is the test — one assertion sweep over all 7 sections and their 41
sub-tabs. **Teeth-verified**: stripping the accessible name from a button in
`RiskHeatmap` makes it fail with `unnamedButton (1)`, and the component was
restored immediately afterwards.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget. 751 tests across 59 files.
