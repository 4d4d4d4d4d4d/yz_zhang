// Spec 61 — compliance posture. Pure.
//
// The shipped posture score was a plain mean over frameworks, which fails in
// three separate ways at once, all of them measurable on the live fixture:
//
//   1. Unweighted. GDPR covers 142 controls and C2PA provenance covers 12, and
//      the mean gave them equal say. Control-weighting moves the headline by up
//      to 8 points, and the direction is not uniform — it depends on where the
//      controls actually sit, which is precisely why guessing is not an option.
//   2. Scope-blind. Global frameworks were folded into every regional filter,
//      so selecting Brazil averaged LGPD (78, caution) with C2PA (100) and
//      reported 89 — the worst market read as the second-best. A regional
//      score must be regional; global coverage is reported beside it, not
//      inside it.
//   3. Averaging away a material failure. The EU AI Act framework sits at 64
//      with `risk` status inside an EU headline of 85. Every audit convention
//      worth the name — SOC 2 opinions, ISO 27001 major nonconformity, CVSS
//      environmental scoring — refuses to let one material exception be
//      diluted by its healthy neighbours. This is the same rule spec 60's
//      go-live gates apply to launch blockers.
//
// And a posture that ignores its own open findings is a snapshot of the last
// audit, not of today, so open risks deduct.

export const STATUS_RANK = { pass: 0, warn: 1, risk: 2 }

// A framework's status caps the headline it can appear inside. Not a
// multiplier: a cap, so the number degrades to a ceiling rather than
// collapsing to zero.
export const STATUS_CAP = { pass: 100, warn: 84, risk: 69 }

// Open findings deduct, bounded so a long tail of low-severity items cannot
// drive posture to zero — the tail is real but it is not an emergency.
export const SEVERITY_DEDUCTION = { high: 6, med: 3, low: 1 }
export const MAX_DEDUCTION = 15

const num = n => (Number.isFinite(Number(n)) ? Number(n) : 0)
const round = n => Math.round(n)

// Which regulatory regime actually governs a market. Regulatory fact, not
// fixture data: a market with no regime in scope has NO coverage, which is a
// different statement from scoring zero, and a different statement again from
// scoring 100.
export const MARKET_SCOPE = { JP: 'JP', DE: 'EU', BR: 'BR', ID: 'SEA', AE: null, MX: null }

// Control-weighted mean. A framework's say in the headline is proportional to
// how much of the control surface it actually covers.
export function weightedScore(frameworks = []) {
  const list = (Array.isArray(frameworks) ? frameworks : []).filter(f => f && num(f.controls) > 0)
  if (!list.length) return null
  const weight = list.reduce((s, f) => s + num(f.controls), 0)
  return weight > 0 ? list.reduce((s, f) => s + num(f.score) * num(f.controls), 0) / weight : null
}

export function worstOf(frameworks = []) {
  return (Array.isArray(frameworks) ? frameworks : []).reduce((worst, f) => {
    if (!f) return worst
    if (!worst) return f
    const a = STATUS_RANK[f.status] ?? 0
    const b = STATUS_RANK[worst.status] ?? 0
    // Same status: the lower score is the more material exception.
    return a > b || (a === b && num(f.score) < num(worst.score)) ? f : worst
  }, null)
}

export function counts(frameworks = []) {
  const out = { pass: 0, warn: 0, risk: 0 }
  for (const f of Array.isArray(frameworks) ? frameworks : []) {
    if (f && out[f.status] !== undefined) out[f.status] += 1
  }
  return out
}

export function deductionsFor(risks = [], table = SEVERITY_DEDUCTION) {
  const items = (Array.isArray(risks) ? risks : [])
    .filter(r => r && table[r.sev] !== undefined)
    .map(r => ({ sev: r.sev, key: r.key ?? r.title, points: table[r.sev] }))
    .sort((a, b) => b.points - a.points)
  const gross = items.reduce((s, i) => s + i.points, 0)
  return { items, gross, applied: Math.min(gross, MAX_DEDUCTION), capped: gross > MAX_DEDUCTION }
}

// `scope` is a region key, or `globalScope` for the whole estate.
export function posture(frameworks = [], { scope = 'all', risks = [], globalScope = 'all' } = {}) {
  const all = (Array.isArray(frameworks) ? frameworks : []).filter(Boolean)
  const isEstate = scope === globalScope
  const regional = isEstate ? all : all.filter(f => f.region === scope)
  const global = isEstate ? [] : all.filter(f => f.region === globalScope)

  const scoped = (Array.isArray(risks) ? risks : []).filter(r => r && (isEstate || r.scope === scope))
  const deduction = deductionsFor(scoped)

  // Saying 100 for an unmeasured scope would be a lie of omission, and saying
  // 0 would be a different one. Both no-regime and no-control-surface report
  // the absence, with the reason attached.
  const uncovered = reason => ({
    scope, covered: false, reason, score: null, raw: null, cap: null, capped: false,
    controls: regional.reduce((s, f) => s + num(f.controls), 0),
    frameworks: regional, global, worst: worstOf(regional),
    counts: counts(regional), contributions: [], deduction, openRisks: scoped
  })

  if (!regional.length) return uncovered('no-regime')

  const raw = weightedScore(regional)
  // Frameworks are listed but none declares a control surface: there is
  // nothing to weight, so there is no score to report.
  if (raw === null) return uncovered('no-controls')
  const worst = worstOf(regional)
  const cap = STATUS_CAP[worst?.status] ?? 100
  const gated = Math.min(raw, cap)
  const score = Math.max(0, gated - deduction.applied)

  return {
    scope,
    covered: true,
    reason: null,
    score: round(score),
    raw: round(raw),
    cap,
    capped: raw > cap,
    controls: regional.reduce((s, f) => s + num(f.controls), 0),
    frameworks: regional,
    global,
    worst,
    counts: counts(regional),
    deduction,
    openRisks: scoped,
    // Weight share per framework, so the panel can show what moves the number
    // instead of asserting it.
    // Reaching here means the control surface is positive, so the share is
    // always well defined.
    contributions: regional.map(f => ({
      name: f.name,
      score: num(f.score),
      controls: num(f.controls),
      share: num(f.controls) / regional.reduce((s, x) => s + num(x.controls), 0)
    })).sort((a, b) => b.share - a.share)
  }
}

export function postureByScope(frameworks = [], scopes = [], risks = [], opts = {}) {
  return (Array.isArray(scopes) ? scopes : []).map(scope => posture(frameworks, { ...opts, scope, risks }))
}

// Posture for a market, resolved through its regulatory regime. Markets with
// no regime in scope come back uncovered rather than silently perfect.
export function postureForMarket(marketCode, frameworks = [], risks = [], map = MARKET_SCOPE) {
  const scope = map[marketCode] ?? null
  if (!scope) {
    return { ...posture(frameworks, { scope: '\u0000none' }), scope: null, market: marketCode, reason: 'no-regime' }
  }
  return { ...posture(frameworks, { scope, risks }), market: marketCode }
}
