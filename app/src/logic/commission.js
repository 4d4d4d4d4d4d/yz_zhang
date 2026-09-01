// Spec 17 — marketplace commission: tier commission with cap enforcement,
// blended rate, earner rollup.

// '∞'/null → Infinity; '$500k' → 500000; '$1.2m' → 1200000; number passes.
// Unparseable → Infinity (fail-open to "no cap" is safe for a ceiling).
export function parseCap(cap) {
  if (cap == null || cap === '∞') return Infinity
  if (typeof cap === 'number') return Number.isFinite(cap) ? cap : Infinity
  const m = String(cap).trim().match(/^\$?\s*([\d.]+)\s*([km])?$/i)
  if (!m) return Infinity
  const n = parseFloat(m[1])
  if (!Number.isFinite(n)) return Infinity
  const mult = m[2]?.toLowerCase() === 'm' ? 1e6 : m[2]?.toLowerCase() === 'k' ? 1e3 : 1
  return n * mult
}

// Aggregate/tier commission — uncapped (a tier's gmv sums many partners;
// the per-partner cap does not apply to the aggregate).
export function tierCommission(gmv, ratePct) {
  return Math.round(Math.max(0, Number(gmv) || 0) * (Number(ratePct) || 0) / 100)
}

// Per-partner commission — the cap lives here.
export function capCommission(gmv, ratePct, cap) {
  const commissionable = Math.min(Math.max(0, Number(gmv) || 0), parseCap(cap))
  return Math.round(commissionable * (Number(ratePct) || 0) / 100)
}

export function blendedRate(tiers = []) {
  const totalGMV = tiers.reduce((s, t) => s + (Number(t.gmv) || 0), 0)
  if (totalGMV <= 0) return 0
  const totalComm = tiers.reduce((s, t) => s + tierCommission(t.gmv, t.rate), 0)
  return Math.round((totalComm / totalGMV) * 10000) / 100
}

export function earnerCommission(earner, tiers = []) {
  const tier = tiers.find(t => t.name === earner.tier)
  if (!tier) return { ...earner, commission: 0, capped: false, unknownTier: true }
  const cap = parseCap(tier.cap)
  return {
    ...earner,
    commission: capCommission(earner.gmv, tier.rate, tier.cap),
    capped: (Number(earner.gmv) || 0) > cap
  }
}

export function commissionRun(tiers = [], earners = []) {
  const byTier = tiers.map(t => ({ ...t, commission: tierCommission(t.gmv, t.rate) }))
  const scoredEarners = earners.map(e => earnerCommission(e, tiers))
  return {
    byTier,
    earners: scoredEarners,
    totalGMV: tiers.reduce((s, t) => s + (Number(t.gmv) || 0), 0),
    totalCommission: byTier.reduce((s, t) => s + t.commission, 0),
    totalPartners: tiers.reduce((s, t) => s + (Number(t.partners) || 0), 0),
    blendedRate: blendedRate(tiers)
  }
}
