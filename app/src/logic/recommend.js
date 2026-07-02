// Spec 01 — AI recommendation: weighted scoring + diversity re-rank + explanations.

export const DEFAULT_WEIGHTS = {
  affinity: 0.28,
  freshness: 0.14,
  performance: 0.26,
  brandFit: 0.14,
  localization: 0.18
}

const SIGNAL_KEYS = Object.keys(DEFAULT_WEIGHTS)

function clamp01(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 0
  return Math.min(1, Math.max(0, n))
}

export function scoreCandidate(candidate, weights = DEFAULT_WEIGHTS) {
  const signals = candidate.signals || {}
  const totalW = SIGNAL_KEYS.reduce((s, k) => s + (weights[k] ?? 0), 0) || 1
  const explanation = SIGNAL_KEYS.map(key => {
    const w = weights[key] ?? 0
    const value = clamp01(signals[key])
    return { key, value, weight: w, contribution: (w * value / totalW) * 100 }
  }).sort((a, b) => b.contribution - a.contribution)
  const score = explanation.reduce((s, e) => s + e.contribution, 0)
  return { score, explanation }
}

// Greedy MMR-lite: pick highest score, then penalize remaining candidates
// that share the picked item's format so a single format can't sweep the top-N.
export function rankCandidates(candidates, { weights = DEFAULT_WEIGHTS, diversityPenalty = 0.15 } = {}) {
  if (!Array.isArray(candidates) || candidates.length === 0) return []
  const pool = candidates.map(c => {
    const { score, explanation } = scoreCandidate(c, weights)
    return { id: c.id, name: c.name, market: c.market, format: c.format, score, adjusted: score, explanation }
  })
  // stable base order: score desc, id asc tiebreak
  const byBase = (a, b) => b.adjusted - a.adjusted || String(a.id).localeCompare(String(b.id))
  const ranked = []
  const remaining = [...pool]
  while (remaining.length) {
    remaining.sort(byBase)
    const picked = remaining.shift()
    ranked.push(picked)
    if (diversityPenalty > 0 && picked.format) {
      for (const r of remaining) {
        if (r.format === picked.format) r.adjusted -= diversityPenalty * r.score
      }
    }
  }
  return ranked.map((r, i) => ({ ...r, rank: i + 1 }))
}
