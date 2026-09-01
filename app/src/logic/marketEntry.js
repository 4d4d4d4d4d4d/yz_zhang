// Spec 60 — market entry scoring. Pure.
//
// Two established frames, kept separate on purpose:
//   * Attractiveness — how big the prize is (GE–McKinsey market attractiveness).
//   * Distance — how hard it is to collect (Ghemawat's CAGE framework, 2001:
//     Cultural, Administrative, Geographic, Economic).
// Most "which market next" dashboards collapse these into one number, which
// hides the case that matters: a huge, fast-growing market you are structurally
// unequipped to serve. Keeping them apart lets the console say *why* a market
// ranks where it does, and lets an operator re-weight one without disturbing
// the other.

export const ATTRACTIVENESS = {
  tam: 0.26,        // addressable ad spend
  growth: 0.22,     // YoY growth of that spend
  digital: 0.18,    // share of commerce that is already online
  payments: 0.16,   // card/wallet penetration — you cannot bill what you cannot charge
  headroom: 0.18    // inverse of competitive intensity: room to win
}

// Distance is friction, not opportunity. Weights follow CAGE's own emphasis:
// administrative and economic distance dominate cross-border B2B outcomes.
export const CAGE = {
  cultural: 0.22,        // language, business norms, buying rituals
  administrative: 0.30,  // licensing, data residency, entity requirements
  geographic: 0.15,      // time zones, logistics, travel for field verification
  economic: 0.33         // price levels, FX volatility, credit risk
}

const ATTR_TOTAL = Object.values(ATTRACTIVENESS).reduce((s, w) => s + w, 0)
const CAGE_TOTAL = Object.values(CAGE).reduce((s, w) => s + w, 0)

const clamp01 = n => Math.min(1, Math.max(0, Number(n) || 0))
const round1 = n => Math.round(n * 10) / 10

// How much of the prize distance is allowed to eat. At 1.0 a maximally distant
// market scores zero, which is wrong — Japan is distant from everywhere and
// people still sell there. 0.55 keeps distance decisive without being fatal.
export const FRICTION_CEILING = 0.55

export function attractivenessOf(market, weights = ATTRACTIVENESS) {
  const parts = Object.entries(weights).map(([key, weight]) => ({
    key,
    weight,
    value: clamp01(market?.[key]),
    points: round1(clamp01(market?.[key]) * weight * 100)
  }))
  const total = parts.reduce((s, p) => s + p.value * p.weight, 0)
  return { score: round1((total / (ATTR_TOTAL || 1)) * 100), parts }
}

export function distanceOf(market, weights = CAGE) {
  const parts = Object.entries(weights).map(([key, weight]) => ({
    key,
    weight,
    value: clamp01(market?.distance?.[key]),
    points: round1(clamp01(market?.distance?.[key]) * weight * 100)
  }))
  const total = parts.reduce((s, p) => s + p.value * p.weight, 0)
  return { score: round1((total / (CAGE_TOTAL || 1)) * 100), parts }
}

// Entry bands. Boundaries belong to the higher band, matching the approval
// matrix in cpq.js so two surfaces do not teach two different conventions.
export const ENTRY_BANDS = [
  { key: 'enter', min: 62 },
  { key: 'pilot', min: 48 },
  { key: 'watch', min: 34 },
  { key: 'defer', min: 0 }
]

export function bandFor(score, bands = ENTRY_BANDS) {
  return (bands.find(b => score >= b.min) ?? bands[bands.length - 1]).key
}

// Months to recover acquisition cost. Gross margin matters: a market where you
// net 40 cents on the dollar takes 2.5x longer to pay back than the headline
// ARPA suggests. Returns null when payback never happens rather than Infinity,
// so the view renders "never" instead of a broken number.
export function paybackMonths(cac, arpaMonthly, grossMarginPct = 100) {
  const c = Number(cac) || 0
  const contribution = (Number(arpaMonthly) || 0) * (clamp01((Number(grossMarginPct) || 0) / 100))
  if (c <= 0) return 0
  if (contribution <= 0) return null
  return round1(c / contribution)
}

export function scoreMarket(market, { attractiveness = ATTRACTIVENESS, cage = CAGE, ceiling = FRICTION_CEILING } = {}) {
  const attr = attractivenessOf(market, attractiveness)
  const dist = distanceOf(market, cage)
  const friction = (dist.score / 100) * clamp01(ceiling)
  const score = round1(attr.score * (1 - friction))
  return {
    code: market?.code,
    name: market?.name,
    attractiveness: attr.score,
    distance: dist.score,
    frictionPct: round1(friction * 100),
    score,
    band: bandFor(score),
    payback: paybackMonths(market?.cac, market?.arpa, market?.grossMargin ?? 100),
    parts: { attractiveness: attr.parts, distance: dist.parts },
    // The single biggest drag, so the panel can name the thing to fix rather
    // than only reporting that the market is hard.
    topBarrier: dist.parts.reduce((worst, p) => (p.points > (worst?.points ?? -1) ? p : worst), null)
  }
}

export function rankMarkets(markets = [], opts = {}) {
  return markets
    .map(m => scoreMarket(m, opts))
    .sort((a, b) => b.score - a.score || a.distance - b.distance || String(a.code).localeCompare(String(b.code)))
}
