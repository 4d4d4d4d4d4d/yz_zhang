# Spec 35 — Sortable & Exportable Console Tables

**Status:** Accepted · **Depends on:** 31 (a11y patterns), 33 (format)

## 1. Problem (critical analysis)

The console has ~20 tabular modules and **none support sorting** — table-stakes
for any operator grid (AG-Grid, TanStack Table, Salesforce all ship it). Worse,
`OrderBook.vue` renders an **"Export CSV" button that does nothing** — a dead
control that lies to the operator. Both are concrete gaps against industry
norms, and both are fixable with one reusable, testable layer.

## 2. Scope

- `logic/sortRows.js` — pure, **stable**, type-aware sort. Numbers compare
  numerically (not `"10" < "2"`), everything else by string; equal keys keep
  input order. `nextDir()` encodes the header-click cycle (new column → asc,
  active column toggles).
- `logic/csv.js` — pure **RFC 4180** serializer. Quotes only when a field holds
  a comma/quote/newline; doubles embedded quotes; CRLF row joins so Excel parses
  cleanly.
- `composables/useSortable.js` — binds `sortRows` to reactive state and exposes
  the `aria-sort` value headers need.
- **Adoption — `OrderBook.vue`:** every column header is now a keyboard-operable
  sort button with `aria-sort` and a direction glyph; the dead Export button now
  downloads the *current sorted+filtered view* as `orders.csv` via a Blob; and
  the GMV/outstanding/overdue/ticket/total figures move onto `useFormat`
  (folds in the spec-33 migration for this surface).

## 3. Review record

**R1 — WYSIWYG export.** The CSV serializes `sorted.value` (post-filter,
post-sort), not the raw source, so what the operator downloads matches what
they see. The column model is shared between the header and the export, so they
can never diverge.

**R2 — accessible headers.** Sorting via a bare `<th @click>` is invisible to
keyboard and screen-reader users. Each header is a real `<button>` inside a
`th[aria-sort]`, so it is focusable, Enter/Space-activatable, and announced.

**R3 — stable sort.** An unstable sort scrambles ties on every re-click, which
reads as a bug. The comparator falls back to the original index, so ties never
move.

**R4 — no new deps.** Sorting and CSV are ~40 lines of pure code; a grid
library would blow the bundle budget for a demo. Reuse over dependency.

## 4. Tests
- `tests/sortRows.test.js`: numeric vs lexical, asc/desc, stability, immutability,
  custom accessor, non-array guard, `nextDir` cycle.
- `tests/csv.test.js`: quoting rules (comma/quote/newline), CRLF joins,
  header-only, label fallback, non-array guards.
- OrderBook wiring covered by the existing mount-smoke sweep.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: clicking a header sorts + flips the glyph and
`aria-sort`, and Export CSV triggers a download of the sorted view.
