// Spec 53 — expansion / upsell propensity. Pure. The score is DERIVED from the
// account's own signals rather than asserted: each signal type carries a weight
// reflecting how predictive it is of expansion, scaled by how strong the signal
// is. Missing signal types genuinely lower the score — an account showing no
// intent is less likely to expand, so the denominator is the full signal set.

export const SIGNAL_WEIGHTS = {
  intent: 0.24,      // explicit buying behaviour — the strongest predictor
  usage: 0.22,       // consumption pressing against the allowance
  pilot: 0.14,       // a time-boxed catalyst with a deadline
  integration: 0.12, // asking about SSO/API is a qualification signal
  team: 0.10,        // seat growth
  client: 0.08,      // agency / sub-client structure the plan doesn't serve
  feature: 0.06,     // adoption gap = room to sell into
  health: 0.04       // relationship quality
}

export const STRENGTH = { high: 1, med: 0.6, low: 0.3 }

const TOTAL_WEIGHT = Object.values(SIGNAL_WEIGHTS).reduce((s, w) => s + w, 0)

// Strongest observation per signal type — listing "usage" twice must not
// double-count. Unknown tags are ignored rather than given phantom weight.
export function strongestByTag(signals) {
  const best = new Map()
  for (const s of Array.isArray(signals) ? signals : []) {
    const w = SIGNAL_WEIGHTS[s?.tag]
    if (w === undefined) continue
    const v = STRENGTH[s?.strength] ?? 0
    if (!best.has(s.tag) || v > best.get(s.tag)) best.set(s.tag, v)
  }
  return best
}

// 0..100. Full marks require every signal type present at high strength.
export function expansionScore(signals) {
  const best = strongestByTag(signals)
  let total = 0
  for (const [tag, value] of best) total += SIGNAL_WEIGHTS[tag] * value
  return Math.round((total / TOTAL_WEIGHT) * 100)
}

// Which signals are moving the score, largest contribution first.
export function scoreBreakdown(signals) {
  const best = strongestByTag(signals)
  return [...best.entries()]
    .map(([tag, value]) => ({
      tag,
      value,
      weight: SIGNAL_WEIGHTS[tag],
      contribution: (SIGNAL_WEIGHTS[tag] * value / TOTAL_WEIGHT) * 100
    }))
    .sort((a, b) => b.contribution - a.contribution || a.tag.localeCompare(b.tag))
}

// Propensity-weighted revenue: what the opportunity is worth once you discount
// it by how likely it is to land. This is what should order a rep's day.
export function expectedValue(score, upside) {
  return ((Number(score) || 0) / 100) * (Number(upside) || 0)
}

export function rankOpportunities(accounts) {
  return (Array.isArray(accounts) ? accounts : [])
    .map(a => {
      const score = expansionScore(a?.signals)
      return { ...a, score, expectedValue: expectedValue(score, a?.upside) }
    })
    .sort((a, b) =>
      b.expectedValue - a.expectedValue ||
      b.score - a.score ||
      String(a.id).localeCompare(String(b.id))
    )
}
