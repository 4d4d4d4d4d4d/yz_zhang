# Spec 32 — Operator Velocity (batch)

**Status:** Accepted · **Depends on:** 20 (registry), 24 (⌘K palette), 27 (store), 31 (g-goto)

## 1. Problem (critical analysis)

Spec 31 shipped `g`-then-key jumps and a WAI-ARIA tablist, but with **zero
discoverability**: nothing tells an operator the shortcuts exist. Every
comparable tool — GitHub, Linear, Gmail, Slack, Jira, Notion — binds `?`
to a keyboard cheat-sheet. Without it, the shortcut layer is invisible and
effectively dead for anyone who didn't read the source.

Second gap: the ⌘K palette (spec 24) opens on an **empty result list**. A
returning operator who lives in three or four modules has to re-type a query
every time. Recent-destination lists (VS Code "recent files", Linear, Slack
quick-switcher) are the standard fix and the store (spec 27) already
persists preferences, so the plumbing exists.

Both are "operator velocity" gaps — help a power user move faster — so they
ship as one cohesive batch.

## 2. Scope

### A. `?` shortcut cheat-sheet
- Pure `shortcutRows()` in `logic/shortcuts.js`: returns global rows
  (`⌘K`, `?`, tablist arrows) plus one `g`-row per `GOTO_MAP` entry,
  each carrying its route target so labels stay registry/i18n-derived.
- `components/ShortcutHelp.vue`: a modal dialog opened by `?` (Shift+/),
  reusing the established overlay a11y pattern — `role="dialog"`,
  `aria-modal`, Esc to close, focus trap, focus return to the opener.
  Suppressed while typing in a field or under ⌘/Ctrl/Alt.
- Goto labels come from i18n (`console.s.<tab>.title`, `nav.home`) so the
  sheet is localized in all four locales and can never drift from the map.

### B. Recent sections in ⌘K
- Pure `logic/recents.js` — `pushRecent(list, item, max=6)`: most-recent-first,
  de-duplicated, capped MRU. No framework, deterministic.
- `store/workspace.js`: persist a `recents` array in prefs; `recordSection(key)`
  applies `pushRecent` and saves. Only registry-valid keys are recorded.
- `components/CommandPalette.vue`: when the query is empty, render recents
  (mapped through the registry to localized labels + routes) as the result
  list, so ↑↓/Enter already work. A "Recent" caption distinguishes them.
- `views/Console.vue`: record the active section on every section change.

## 3. Review record

**R1 — cheat-sheet source of truth.** Rejected a hand-written shortcut table
(drifts from `GOTO_MAP`). The goto rows are *generated* from the map; a test
asserts every map key appears exactly once, so adding a section to the
registry auto-appears in the sheet.

**R2 — `?` vs a visible button.** Kept `?` (industry muscle-memory) but the
sheet also lists itself (`? → this dialog`) so it is self-documenting once
found; the footer of ⌘K already advertises ⌘K, and the sheet is reachable
from there conceptually. No new persistent chrome added (bundle discipline).

**R3 — recents storage.** Store keys only, not labels or routes — labels are
locale-dependent and routes are derivable from the registry, so persisting
them would rot across releases/locales. On read, unknown keys are filtered
out, so a renamed/removed section can never break the palette.

**R4 — recents cap.** 6, matching the count of primary sections a power user
realistically rotates through; larger lists turn the empty-query palette into
noise. Duplicates collapse to a single most-recent entry.

## 4. Tests
- `tests/shortcuts.test.js` (extended): `shortcutRows()` covers every
  `GOTO_MAP` key exactly once, includes the global rows, and every goto row
  carries a valid route target.
- `tests/recents.test.js`: MRU order, de-dup to front, cap, immutability of
  input, empty/whitespace ignored.
- `tests/subtabs.test.js` unchanged. Component wiring covered by the existing
  mount-smoke; `ShortcutHelp` added to that sweep.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `npm run check:bundle`
within 250 KB, plus a browser smoke: `?` opens/closes the sheet with focus
return, and ⌘K on an empty query shows the last-visited sections.
