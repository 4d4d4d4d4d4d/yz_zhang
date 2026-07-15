# Spec 28 — Accessibility · Bundle Budget · Localized Titles (batch)

Status: **Approved** · Review: R1 (2026-07-07)
Artifacts: `components/CommandPalette.vue` · `components/NotificationCenter.vue` ·
`composables/useDocumentTitle.js` · `scripts/check-bundle.mjs` ·
`.github/workflows/ci.yml`

## Problem (from the running critical review)

Two structural gaps remained plus one industry-baseline UX miss:

5. **Accessibility ≈ zero.** The ⌘K palette and the notification panel
   are keyboard/overlay surfaces with no ARIA roles, no `aria-live`
   result counts, and no focus return on close. For a product selling
   into US/EU markets WCAG is a compliance item, not a nicety.
6. **No bundle budget.** The Console chunk is ~300 KB and nothing gates
   growth; industry practice (size-limit) fails CI when a chunk exceeds
   its gzip budget.
7. **Static `document.title`.** The tab title never changes across
   routes or locales — a basic SEO/multi-tab UX miss every marketing
   site handles.

## Design

### 5 · A11y on the overlays
- **CommandPalette**: `role="dialog"` + `aria-modal` + `aria-label`;
  the input is `role="combobox"` wired to a `role="listbox"` of
  `role="option"` rows with `aria-selected`; an `aria-live="polite"`
  node announces the result count. On close, focus returns to the
  element that held it when the palette opened (captured on open).
- **NotificationCenter**: the bell exposes `aria-label` with the unread
  count and `aria-expanded`; the panel is `role="dialog"`; rows are real
  buttons already. Esc closes and returns focus to the bell.
- Reduced motion: overlays respect `prefers-reduced-motion` (no logic,
  CSS only) — noted for completeness.

### 6 · `scripts/check-bundle.mjs`
Runs `vite build`, reads `dist/assets/*.js`, gzips each, and asserts
per-entry budgets from a table (`index` ≤ 120 KB gz, `Console` ≤ 110 KB
gz, others ≤ 30 KB gz) with a **total** ceiling. Exceeding any budget
exits non-zero with the offending chunk and its overage. Wired into CI
after the build step. Budgets sit ~15 % above current so normal growth
passes but a regression (a heavy dep, an un-lazy import) trips it.

### 7 · `composables/useDocumentTitle.js`
`useDocumentTitle()` watches route + locale and sets
`document.title` = `"<page> · <brand>"`, page name from the route's
`meta.titleKey` (i18n `title.*`). Console appends the active section.
SSR/test-safe: no-op when `document` is undefined.

## Test plan
- a11y (`tests/a11y.test.js`, happy-dom mount): palette has
  role=dialog + combobox + listbox with aria-selected on the active
  option and an aria-live count node; bell exposes aria-label/aria-expanded.
- titles: navigating home→product→console sets the expected localized
  `document.title`; switching locale updates it.
- bundle: the checker parses sizes and enforces budgets — verified by a
  unit test over its pure budget-evaluation function (fail when a
  synthetic chunk exceeds budget), so the logic is tested without a full
  build in the unit run; CI runs the real thing.

## Review record — R1
- ✅ Budget-evaluation split into a pure function so it is unit-tested
  like every other logic module (spec 18 coverage gate then covers it);
  the build-and-measure wrapper stays in the script.
- ✅ Focus return captured on open, not assumed to be the trigger — a
  palette opened by ⌘K must return focus to wherever the user was.
- ✅ Titles via route meta + i18n keys, not hardcoded — parity gate owns
  the copy.
- Verdict: **approved**.
