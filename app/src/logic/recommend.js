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

// Spec 50 — map a concept plus the operator's brief to the 0..1 signal vector
// the scorer consumes. This is what makes the console's inputs actually drive
// the ranking: goal selects which performance metric matters, audience drives
// affinity, voice drives brand fit, and a budget that cannot fund a concept
// discounts the performance it could realistically deliver.
export const GOAL_METRIC = {
  roas:  { key: 'roas', cap: 7 },
  cpa:   { key: 'cvr',  cap: 5 },
  reach: { key: 'ctr',  cap: 6 }
}

export function conceptSignals(concept = {}, ctx = {}) {
  const { audience = [], voice = null, goal = 'roas', budget = Infinity } = ctx
  const metric = GOAL_METRIC[goal] ?? GOAL_METRIC.roas
  const rawPerf = clamp01((Number(concept[metric.key]) || 0) / metric.cap)

  // A concept the brief cannot fund cannot deliver its headline performance.
  const needed = Number(concept.minBudget) || 0
  const fundable = needed <= 0 ? 1 : clamp01((Number(budget) || 0) / needed)

  const targets = Array.isArray(concept.audiences) ? concept.audiences : []
  const wanted = Array.isArray(audience) ? audience : []
  const affinity = wanted.length
    ? wanted.filter(a => targets.includes(a)).length / wanted.length
    : 0.5 // no audience selected → neutral, not zero

  return {
    affinity,
    freshness: clamp01((concept.scores?.creativity ?? 0) / 100),
    performance: rawPerf * fundable,
    brandFit: concept.voice === voice ? 1 : 0.45,
    localization: clamp01((concept.scores?.fit ?? 0) / 100)
  }
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
