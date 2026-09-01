# Spec 39 — Command Palette Actions

**Status:** Accepted · **Depends on:** 24 (palette), 38 (motion), i18n

## 1. Problem (critical analysis)

The ⌘K palette (spec 24) only **navigates** — but every command palette worth
the name (Linear, VS Code, Raycast) also **runs actions**. Meanwhile specs 38
and the locale switcher added global, store-backed operations (set motion,
switch language) that are only reachable by hunting through the navbar. The
palette is the obvious home for them: type "motion" or "日本語", hit Enter, done.

## 2. Scope

- `logic/commands.js` — pure `buildActionCommands({ locales, motionPrefs })` →
  descriptors `{ id, kind, arg }`, one per language and per motion pref. No
  labels, no side effects (spec 00 §2).
- `CommandPalette.vue` — action entries (labels resolved via i18n, rebuilt on
  locale change) are merged into the searchable index after the modules. `go()`
  runs an action when the entry carries one (`setLocale` / `setMotionPref`),
  otherwise routes as before. Actions are tagged "Action" in the row.
- i18n: `cmd.action` / `cmd.language` / `cmd.motion` across all four locales;
  action labels reuse the existing `motion.*` and `locales` names.

## 3. Review record

**R1 — descriptors in logic, execution in the view.** The logic layer can't
import vue-router/i18n, so it emits inert `{kind, arg}` and the palette owns the
handler map. This mirrors the search label-injection pattern (spec 24) and keeps
`architecture.test.js` green.

**R2 — one index, existing search.** Actions reuse the same `{label, haystack}`
shape modules use, so `searchModules` scores them with zero new search code;
they surface only when the query matches ("motion", "language", a locale name),
never cluttering the empty-query recents/browse view.

**R3 — labels rebuild on locale.** `actionEntries` reads `locale.value` so
switching language via the palette immediately re-labels the remaining actions.

## 4. Tests
`tests/commands.test.js`: one action per locale + per pref, unique `act:`-namespaced
ids, empty-input defaults. Palette wiring (merge + execute) covered by the
mount-smoke sweep; i18n parity by `tests/i18n.test.js`.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: ⌘K → type "motion" → an action runs and flips
`data-reduce-motion`; type a language name → the UI re-localizes.
