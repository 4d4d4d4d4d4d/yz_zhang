// Spec 03 — partner matchmaking: weighted fit scoring with reasons.

export const WEIGHTS = { category: 0.30, market: 0.30, stage: 0.15, trust: 0.25 }

const STAGES = ['seed', 'growth', 'scale', 'enterprise']

function jaccard(a = [], b = []) {
  const A = new Set(a), B = new Set(b)
  if (A.size === 0 && B.size === 0) return 0
  let inter = 0
  for (const x of A) if (B.has(x)) inter++
  return inter / (A.size + B.size - inter)
}

// Exact target market = 1, adjacent region = 0.5; take the best per target.
function marketFit(targets = [], partnerMarkets = [], adjacency = {}) {
  if (targets.length === 0) return 0
  const pm = new Set(partnerMarkets)
  let sum = 0
  for (const t of targets) {
    if (pm.has(t)) { sum += 1; continue }
    const adj = adjacency[t] || []
    if (adj.some(m => pm.has(m))) sum += 0.5
  }
  return sum / targets.length
}

function stageFit(a, b) {
  const ia = STAGES.indexOf(a), ib = STAGES.indexOf(b)
  if (ia < 0 || ib < 0) return 0
  const d = Math.abs(ia - ib)
  return d === 0 ? 1 : d === 1 ? 0.5 : 0
}

export function scorePartner(need, partner, { adjacency = {} } = {}) {
  const factors = {
    category: jaccard(need.categories, partner.categories),
    market: marketFit(need.markets, partner.markets, adjacency),
    stage: stageFit(need.stage, partner.stage),
    trust: Math.min(1, Math.max(0, Number(partner.trust) || 0))
  }
  const score = Math.round(
    Object.entries(WEIGHTS).reduce((s, [k, w]) => s + w * factors[k], 0) * 100
  )
  const tier = score >= 75 ? 'strong' : score >= 55 ? 'good' : score >= 35 ? 'explore' : 'weak'
  const reasons = Object.entries(factors)
    .filter(([, v]) => v > 0)
    .sort((a, b) => WEIGHTS[b[0]] * b[1] - WEIGHTS[a[0]] * a[1])
    .slice(0, 3)
    .map(([k, v]) => REASON_TEXT[k](v, partner))
  return { score, tier, factors, reasons }
}

const REASON_TEXT = {
  category: v => `Category overlap ${(v * 100).toFixed(0)}% — shared vertical expertise to open with`,
  market: v => `Active in ${(v * 100).toFixed(0)}% of your target markets — local presence from day one`,
  stage: v => (v === 1 ? 'Same growth stage — aligned deal sizes and timelines' : 'Adjacent stage — mentorship or scale-up dynamic'),
  trust: (v, p) => `Verification score ${(v * 100).toFixed(0)} — ${p.verified ? 'KYB & showcase verified' : 'partially verified'}`
}

export function rankPartners(need, partners, { topN = 10, includeWeak = false, adjacency = {} } = {}) {
  const scored = (partners || []).map(p => ({ partner: p, ...scorePartner(need, p, { adjacency }) }))
  return scored
    .filter(s => includeWeak || s.tier !== 'weak')
    .sort((a, b) => b.score - a.score || b.factors.trust - a.factors.trust || String(a.partner.id).localeCompare(String(b.partner.id)))
    .slice(0, topN)
}
