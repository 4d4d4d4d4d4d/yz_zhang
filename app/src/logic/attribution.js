// Spec 46 — multi-touch attribution. Pure: credit is COMPUTED from customer
// journeys (ordered touchpoints + conversion time), not read from a table.
// A journey is { touches: [{ channel, at }], convertedAt, count }, where
// `count` aggregates identical paths (standard path-rollup) and defaults to 1.

export const MODELS = ['first', 'last', 'linear', 'decay', 'position', 'shapley']

const DAY = 86400000

function validJourneys(journeys) {
  return (Array.isArray(journeys) ? journeys : []).filter(
    j => j && Array.isArray(j.touches) && j.touches.length > 0
  )
}

const weightOf = j => (Number.isFinite(j.count) && j.count > 0 ? j.count : 1)

// Per-journey credit vector (sums to 1) for the rule-based models.
function journeyCredit(journey, model, { halfLifeDays = 7 } = {}) {
  const t = journey.touches
  const n = t.length
  const out = new Array(n).fill(0)

  if (model === 'first') { out[0] = 1; return out }
  if (model === 'last') { out[n - 1] = 1; return out }
  if (model === 'linear') return out.fill(1 / n)

  if (model === 'decay') {
    const end = Number.isFinite(journey.convertedAt) ? journey.convertedAt : t[n - 1].at
    const w = t.map(x => Math.pow(2, -Math.max(0, end - (Number(x.at) || 0)) / (halfLifeDays * DAY)))
    const sum = w.reduce((s, v) => s + v, 0)
    return sum > 0 ? w.map(v => v / sum) : out.fill(1 / n)
  }

  if (model === 'position') {
    if (n === 1) { out[0] = 1; return out }
    if (n === 2) { out[0] = 0.5; out[1] = 0.5; return out }
    out[0] = 0.4
    out[n - 1] = 0.4
    for (let i = 1; i < n - 1; i++) out[i] = 0.2 / (n - 2)
    return out
  }

  return out.fill(1 / n) // unknown model → linear, never NaN
}

// Shapley value over channel coalitions. Characteristic function
// v(S) = converting weight from journeys whose channel set is a subset of S.
function shapleyCredit(journeys, channels) {
  const n = channels.length
  if (n === 0) return {}
  const index = new Map(channels.map((c, i) => [c, i]))

  // Bitmask of distinct channels per journey.
  const paths = journeys.map(j => {
    let mask = 0
    for (const touch of j.touches) {
      const i = index.get(touch.channel)
      if (i !== undefined) mask |= 1 << i
    }
    return { mask, weight: weightOf(j) }
  }).filter(p => p.mask !== 0)

  const v = new Array(1 << n).fill(0)
  for (let S = 0; S < (1 << n); S++) {
    let total = 0
    for (const p of paths) if ((p.mask & ~S) === 0) total += p.weight
    v[S] = total
  }

  const fact = [1]
  for (let i = 1; i <= n; i++) fact[i] = fact[i - 1] * i

  const phi = new Array(n).fill(0)
  for (let i = 0; i < n; i++) {
    const bit = 1 << i
    for (let S = 0; S < (1 << n); S++) {
      if (S & bit) continue // subsets excluding i
      let size = 0
      for (let k = 0; k < n; k++) if (S & (1 << k)) size++
      const weight = (fact[size] * fact[n - size - 1]) / fact[n]
      phi[i] += weight * (v[S | bit] - v[S])
    }
  }

  const out = {}
  channels.forEach((c, i) => { out[c] = Math.max(0, phi[i]) })
  return out
}

// Credit per channel, normalized to fractions summing to 1 (empty when there
// is nothing to attribute).
export function attribute(journeys, model = 'linear', opts = {}) {
  const js = validJourneys(journeys)
  if (js.length === 0) return {}

  const channels = []
  for (const j of js) for (const t of j.touches) {
    if (t && t.channel != null && !channels.includes(t.channel)) channels.push(t.channel)
  }
  if (channels.length === 0) return {}

  const raw = {}
  for (const c of channels) raw[c] = 0

  if (model === 'shapley') {
    Object.assign(raw, shapleyCredit(js, channels))
  } else {
    for (const j of js) {
      const credit = journeyCredit(j, model, opts)
      const w = weightOf(j)
      j.touches.forEach((t, i) => {
        if (t && t.channel != null) raw[t.channel] += credit[i] * w
      })
    }
  }

  const total = Object.values(raw).reduce((s, v) => s + v, 0)
  if (!(total > 0)) return {}
  const out = {}
  for (const c of channels) out[c] = raw[c] / total
  return out
}

// Ranked rows for a table/chart: [{ channel, credit, pct }] desc by credit.
export function attributionRows(journeys, model = 'linear', opts = {}) {
  const credit = attribute(journeys, model, opts)
  return Object.entries(credit)
    .map(([channel, c]) => ({ channel, credit: c, pct: c * 100 }))
    .sort((a, b) => b.credit - a.credit || a.channel.localeCompare(b.channel))
}
