# Spec 31 — Console Keyboard Navigation & A11y (batch): Tablist · Skip-Link · G-Goto

Status: **Approved** · Review: R1 (2026-07-07)
Domains: `components/SubTabs.vue` · `App.vue` · `logic/shortcuts.js` ·
`components/GotoShortcuts.vue`

## Problem (v26 critical review)

Overlays got ARIA in spec 28, but the console's **primary** navigation
did not:

1. `SubTabs` — the sub-tab bar under every one of 7 sections — is a row
   of plain `<button>`s. No `role="tablist"`, no `aria-selected`, no
   arrow-key movement, no roving tabindex. It is the highest-traffic
   interactive surface in the product and it fails the WAI-ARIA Tabs
   pattern outright.
2. No **skip-to-content** link (WCAG 2.4.1) — a keyboard/AT user must tab
   through the whole navbar on every page.

And an industry-baseline power feature is missing:

3. **G-goto shortcuts.** GitHub/Linear-style `g` then a key to jump
   between top-level areas. The product sells a keyboard-first console
   but only has ⌘K; operators expect `g` + section.

## Design

### 1 · `SubTabs` → WAI-ARIA Tabs pattern
- Container `role="tablist"`; each tab `role="tab"` with `aria-selected`,
  `tabindex` roving (0 on the selected tab, −1 on the rest).
- Keyboard: ← / → move selection (wrapping), Home / End jump to first /
  last; moving selects and focuses (automatic-activation tabs). Click
  unchanged.
- Purely presentational contract preserved (`modelValue` / `update`).

### 2 · Skip-link
- First focusable element in `App.vue`: an anchor to `#main` that is
  visually hidden until focused, then reveals at top-left. `<main>` gets
  `id="main"` and `tabindex="-1"` so the link can move focus into it.
  Copy `nav.skip` ×4 locales.

### 3 · `logic/shortcuts.js` + `GotoShortcuts.vue`
- `resolveGoto(key)` — pure: maps a single key to a console section route
  from a fixed map (`h`→home, and section initials that don't collide:
  `r`ecommend, `m`arketing, `p`artners, `d`eals, `s`howcase, `i`mmersive,
  `t`rust). Unknown key → null. The map is derived from the SECTIONS
  registry order with a hand-checked letter per section (collisions
  resolved once, asserted by test).
- `GotoShortcuts.vue` — a global listener: pressing `g` arms a 1.5s
  window; the next key runs `resolveGoto` and navigates, else disarms.
  Ignored while typing in an input/textarea or when a modifier is held
  (so ⌘K and normal typing are unaffected). Mounted once in App.

## Test plan
- shortcuts: every section has a unique, non-colliding key; `resolveGoto`
  maps each and returns null for unknown/space; the map covers exactly
  the registry sections plus home.
- tablist (happy-dom mount of SubTabs): role=tablist/tab present, exactly
  one aria-selected, roving tabindex (selected 0, others −1); ArrowRight
  from the last tab wraps to the first and emits the update; Home/End.
- Browser: Tab from page top reveals the skip link and it moves focus to
  main; arrow keys move sub-tabs; `g` then `t` lands on Trust Center.

## Review record — R1
- ✅ Automatic-activation tabs (move = select) chosen over manual — the
  sub-tabs have no expensive mount and it matches the existing click
  behavior; simplest correct pattern.
- ✅ Goto letters hand-assigned and test-locked against collision rather
  than first-initial-derived (immersive/inputs, etc. would clash);
  regenerating the map can't silently double-book a key.
- ✅ Shortcuts suppressed in text fields and under modifiers so they
  never fight ⌘K or typing.
- Verdict: **approved**.
