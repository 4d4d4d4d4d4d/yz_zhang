// Spec 32 — most-recently-used list for the ⌘K empty-query jump list.
// Pure, framework-free, deterministic. Stores opaque keys only; the view
// maps them to localized labels + routes through the registry.

// Returns a NEW most-recent-first, de-duplicated, capped list. The input
// array is never mutated. Empty/whitespace items are ignored.
export function pushRecent(list, item, max = 6) {
  const key = String(item ?? '').trim()
  if (!key) return Array.isArray(list) ? list.slice(0, max) : []
  const rest = (Array.isArray(list) ? list : []).filter(k => k !== key)
  return [key, ...rest].slice(0, max)
}
