// Spec 24 — command-palette search. Registry-driven index with an
// injected label resolver (the logic layer never imports vue-i18n).

export function buildIndex(sections, labelOf) {
  const entries = []
  for (const s of sections) {
    const sectionLabel = labelOf('section', s.key)
    entries.push({
      id: s.key,
      section: s.key,
      sub: null,
      label: sectionLabel,
      sectionLabel,
      route: { name: 'console', params: { tab: s.key } },
      haystack: `${sectionLabel} ${s.key}`.toLowerCase()
    })
    for (const sub of s.subs) {
      const label = labelOf('tab', `${s.key}.${sub}`)
      entries.push({
        id: `${s.key}/${sub}`,
        section: s.key,
        sub,
        label,
        sectionLabel,
        route: { name: 'console', params: { tab: s.key }, query: { sub } },
        haystack: `${label} ${sectionLabel} ${sub} ${s.key}`.toLowerCase()
      })
    }
  }
  return entries
}

function subsequence(query, text) {
  let qi = 0
  for (const ch of text) {
    if (ch === query[qi]) qi++
    if (qi === query.length) return true
  }
  return false
}

export function scoreEntry(query, entry) {
  const label = entry.label.toLowerCase()
  if (label === query) return 100
  if (label.startsWith(query)) return 80
  if (label.split(/[\s·]+/).some(w => w.startsWith(query))) return 70
  if (entry.haystack.includes(query)) return 50
  if (subsequence(query, entry.haystack)) return 25
  return 0
}

export function searchModules(query, index, { limit = 8 } = {}) {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return index.slice(0, limit) // browse mode
  return index
    .map((entry, i) => ({ entry, score: scoreEntry(q, entry), i }))
    .filter(r => r.score > 0)
    .sort((a, b) => b.score - a.score || a.entry.label.length - b.entry.label.length || a.i - b.i)
    .slice(0, limit)
    .map(r => r.entry)
}
