# Spec 24 — ⌘K Command Palette: Registry-Driven Global Search

Status: **Approved** · Review: R1 (2026-07-05)
Domains: `logic/search.js` · `components/CommandPalette.vue` · `App.vue`

## Problem

The console has grown to 7 sections × 44 modules. The only way to reach
one is sidebar + sub-tab clicking — up to three interactions with no
recall support. Industry-standard operator consoles (Stripe, Linear,
Notion) solve this with a keyboard-first command palette (⌘K): type a few
characters, jump anywhere. For a multilingual operator base (出海 teams),
search must match the operator's *own language*, not just English.

## Design — `logic/search.js` (pure, testable)

### `buildIndex(sections, labelOf)`
- Input: the single-source `SECTIONS` registry (spec 20) plus a
  `labelOf(kind, path)` resolver the caller backs with i18n (`console.s.*`
  titles, `console.tabs.*` labels). The logic layer stays free of vue-i18n
  (spec 00 §2 / spec 22 isolation — the resolver is injected).
- Output entries: `{ id: 'section/sub', section, sub, label, sectionLabel,
  route: { name:'console', params:{ tab }} , haystack }` where haystack
  combines label + sectionLabel + raw keys (so `revrec`, `收入确认` and
  "Rev recognition" all hit). Sections themselves are entries too
  (`sub: null`).

### `searchModules(query, index, { limit = 8 })`
Scoring per entry over the normalized (lowercased, trimmed) query:
- exact label match 100 · label prefix 80 · word prefix 70 ·
  substring 50 · subsequence (fuzzy, in-order chars) 25 · else 0.
- Score ties break by shorter label, then index order (registry order).
- Empty/whitespace query → the first `limit` entries in registry order
  (browse mode, palette never renders empty).
- CJK note: prefix/substring operate on code points, so 中文/日本語
  labels match naturally; subsequence gives forgiving pinyin-free recall.

## Design — `CommandPalette.vue`
- Global overlay teleported to body; opened by **⌘K / Ctrl+K** (and a
  navbar button for discoverability), closed by **Esc** or backdrop.
- Arrow keys move the active row; **Enter** routes to the target
  (`/console/:tab` + preselect sub-tab via query `?sub=`), palette closes.
- Console honors `?sub=` on mount (deep-linkable sub-tabs — a side
  benefit industry consoles also ship).
- Copy (`palette.*`: placeholder, empty state, hint) in i18n ×4 — the
  spec-14 parity gate enforces completeness.
- Mounted once in `App.vue`; the mount smoke (spec 21) and navigation
  smoke (spec 23) cover it automatically.

## Test plan
- buildIndex: 7 section entries + 44 sub entries; labels resolved via the
  injected resolver; raw keys present in haystacks.
- search: exact > prefix > substring > subsequence ordering; zh query
  matches zh labels; raw-key query (`revrec`) hits; empty query returns
  browse list; no match → `[]`; limit respected.
- Browser: ⌘K opens, typing filters, Enter lands on the right console
  sub-tab, Esc closes; zh locale search in Chinese works.

## Review record — R1
- ✅ Label resolver injected rather than importing vue-i18n in the logic
  layer — keeps spec 22's isolation gate green by design, not exception.
- ✅ `?sub=` deep links added so palette hits (and future share links) can
  target a sub-tab, not just a section.
- Verdict: **approved**.
