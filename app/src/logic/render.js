// Spec 13 R2 — render plan builder + simulated progress, extracted from
// RenderStudio.vue. Progress randomness is injected.

// Cartesian market × format expansion. Unknown ids are reported in
// skipped[], never silently dropped.
export function buildRenderPlan({ targets = [], formats = [] } = {}, catalog = {}) {
  const marketById = new Map((catalog.markets || []).map(m => [m.id, m]))
  const formatById = new Map((catalog.formats || []).map(f => [f.id, f]))
  const items = []
  const skipped = []
  for (const m of targets) {
    const mk = marketById.get(m)
    if (!mk) { skipped.push({ kind: 'market', id: m }); continue }
    for (const f of formats) {
      const fm = formatById.get(f)
      if (!fm) {
        if (!skipped.some(s => s.kind === 'format' && s.id === f)) skipped.push({ kind: 'format', id: f })
        continue
      }
      items.push({ id: `${m}-${f}`, market: mk.label, lang: mk.lang, format: fm.label, progress: 0 })
    }
  }
  return { items, skipped, planned: items.length }
}

// One tick of simulated render progress: +8 to +22, capped at 100.
export function advanceProgress(progress, rng = Math.random) {
  return Math.min(100, progress + 8 + rng() * 14)
}
