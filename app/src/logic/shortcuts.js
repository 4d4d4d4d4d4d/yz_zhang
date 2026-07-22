// Spec 31 — g-goto keyboard shortcuts. Pure key→route resolver.
// Letters hand-assigned and collision-free across the console sections
// (test-locked); regenerating from initials would double-book (immersive
// vs inputs, etc.), so the map is explicit.

export const GOTO_MAP = {
  h: { name: 'home' },
  r: { name: 'console', params: { tab: 'recommend' } },
  m: { name: 'console', params: { tab: 'marketing' } },
  p: { name: 'console', params: { tab: 'partners' } },
  d: { name: 'console', params: { tab: 'deals' } },
  s: { name: 'console', params: { tab: 'showcase' } },
  i: { name: 'console', params: { tab: 'immersive' } },
  t: { name: 'console', params: { tab: 'trust' } }
}

export function resolveGoto(key) {
  return GOTO_MAP[String(key || '').toLowerCase()] ?? null
}

// Spec 32 — rows for the `?` cheat-sheet. Global rows are static; the goto
// rows are GENERATED from GOTO_MAP so the sheet can never drift from the
// live shortcut layer. Labels are resolved by the view via i18n/registry —
// this stays framework-free and deterministic.
export function shortcutRows() {
  const global = [
    { id: 'palette', keys: ['⌘', 'K'] },
    { id: 'help', keys: ['?'] },
    { id: 'tabs', keys: ['←', '→'] }
  ]
  const goto = Object.entries(GOTO_MAP).map(([key, route]) => ({
    id: route.name === 'home' ? 'home' : `tab:${route.params.tab}`,
    keys: ['g', key],
    route
  }))
  return { global, goto }
}
