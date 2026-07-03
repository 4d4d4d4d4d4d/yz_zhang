// Spec 13 R4 — what-if budget forecasting, extracted from ForecastSim.vue.
// Channel model: { id, k, sat } — saturating revenue in $thousands.

// r(b) = k · sat · (1 − e^{−b/sat})
export function saturatingRevenue(ch, budgetK) {
  return ch.k * ch.sat * (1 - Math.exp(-budgetK / ch.sat))
}

// dr/db = k · e^{−b/sat}
export function marginalRoas(ch, budgetK) {
  return ch.k * Math.exp(-budgetK / ch.sat)
}

// Per-channel projections + portfolio totals. Channels carry alloc (%).
export function project(channels, totalBudget) {
  const rows = channels.map(c => {
    const budgetK = (totalBudget * c.alloc / 100) / 1000
    const revK = saturatingRevenue(c, budgetK)
    return {
      id: c.id,
      budget: budgetK * 1000,
      revenue: revK * 1000,
      marginal: marginalRoas(c, budgetK),
      roas: budgetK > 0 ? revK / budgetK : 0
    }
  })
  const totalRevenue = rows.reduce((s, r) => s + r.revenue, 0)
  return { rows, totalRevenue, totalRoas: totalBudget > 0 ? totalRevenue / totalBudget : 0 }
}

// Slider move: set channel `id` to `val`%, shrink/grow the others
// proportionally, and repair rounding drift so the sum is exactly 100.
// Returns { id: alloc } — callers apply it to their own state.
export function rebalanceAllocations(channels, id, val) {
  const next = Object.fromEntries(channels.map(c => [c.id, c.alloc]))
  if (!(id in next)) return next
  const clamped = Math.min(100, Math.max(0, Math.round(val)))
  const diff = clamped - next[id]
  next[id] = clamped
  const others = channels.filter(c => c.id !== id)
  const pool = others.reduce((s, c) => s + next[c.id], 0)
  if (pool > 0) {
    for (const c of others) {
      next[c.id] = Math.max(0, Math.round(next[c.id] - diff * (next[c.id] / pool)))
    }
  }
  const sum = Object.values(next).reduce((s, v) => s + v, 0)
  if (sum !== 100) {
    const repair = others.find(c => next[c.id] > 0) || channels.find(c => c.id !== id) || channels[0]
    next[repair.id] += 100 - sum
  }
  return next
}

// λ-sweep water-fill: budget each channel to sat·ln(k/λ) (0 when λ ≥ k),
// scan λ for the split matching the total, keep the best-revenue hit.
// Falls back to the current allocation shape only if no λ lands within
// tolerance (kept from the original; tolerance 2%).
export function optimalAllocation(channels, totalBudget) {
  const totalK = totalBudget / 1000
  let best = null
  let bestRev = -Infinity
  for (let iter = 0; iter < 200; iter++) {
    const lambda = 0.05 + iter * 0.025
    const budgets = channels.map(c => (lambda >= c.k ? 0 : c.sat * Math.log(c.k / lambda)))
    const sum = budgets.reduce((s, b) => s + b, 0)
    if (sum <= 0 || Math.abs(sum - totalK) / totalK >= 0.02) continue
    const rev = budgets.reduce((s, b, i) => s + saturatingRevenue(channels[i], b), 0)
    if (rev > bestRev) {
      bestRev = rev
      best = budgets.map(b => Math.round((b / sum) * 100))
    }
  }
  if (!best) return null
  const drift = 100 - best.reduce((s, b) => s + b, 0)
  best[0] += drift
  return Object.fromEntries(channels.map((c, i) => [c.id, best[i]]))
}
