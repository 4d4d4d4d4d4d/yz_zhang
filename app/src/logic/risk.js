// Spec 52 — enterprise risk scoring (ISO 31000 shape). Pure. A likelihood ×
// impact matrix is only half the story: a board asks how much the controls
// actually buy you (control effectiveness) and which residual risks sit above
// the organisation's stated appetite. Both are computed here.

export const SCALE_MAX = 5
export const MAX_SCORE = SCALE_MAX * SCALE_MAX // 25
export const DEFAULT_APPETITE = 8 // residual score a risk may not exceed

const clampScale = v => {
  const n = Number(v)
  if (!Number.isFinite(n)) return 0
  return Math.min(SCALE_MAX, Math.max(0, n))
}

export function riskScore(likelihood, impact) {
  return clampScale(likelihood) * clampScale(impact)
}

// Bands over a 1..25 multiplicative matrix.
export function severityBand(score) {
  const s = Number(score) || 0
  if (s >= 16) return 'critical'
  if (s >= 12) return 'high'
  if (s >= 6) return 'med'
  return 'low'
}

// Fraction of inherent risk removed by the controls, in [0,1]. Null when there
// was no inherent risk to reduce — a reduction ratio needs a denominator.
export function controlEffectiveness(inherentScore, residualScore) {
  const inherent = Number(inherentScore) || 0
  if (!(inherent > 0)) return null
  const reduction = (inherent - (Number(residualScore) || 0)) / inherent
  return Math.min(1, Math.max(0, reduction))
}

// Residual above appetite = escalate. Equal to appetite is within tolerance.
export function exceedsAppetite(residualScore, appetite = DEFAULT_APPETITE) {
  return (Number(residualScore) || 0) > (Number(appetite) || 0)
}

// Data hygiene: controls cannot raise risk. Surfaced, never silently clamped
// away, so a bad register entry stays visible.
export function auditRisks(risks) {
  return (Array.isArray(risks) ? risks : [])
    .filter(r => riskScore(r?.r?.l, r?.r?.p) > riskScore(r?.i?.l, r?.i?.p))
    .map(r => ({ id: r.id, issue: 'residual-exceeds-inherent' }))
}

export function assessRisk(risk = {}, appetite = DEFAULT_APPETITE) {
  const inherent = riskScore(risk?.i?.l, risk?.i?.p)
  const residual = riskScore(risk?.r?.l, risk?.r?.p)
  return {
    id: risk.id,
    inherent,
    residual,
    inherentBand: severityBand(inherent),
    residualBand: severityBand(residual),
    effectiveness: controlEffectiveness(inherent, residual),
    breach: exceedsAppetite(residual, appetite)
  }
}

export function portfolioRisk(risks, { appetite = DEFAULT_APPETITE } = {}) {
  const list = (Array.isArray(risks) ? risks : []).map(r => assessRisk(r, appetite))
  const measurable = list.filter(r => r.effectiveness !== null)
  const totalInherent = list.reduce((s, r) => s + r.inherent, 0)
  const totalResidual = list.reduce((s, r) => s + r.residual, 0)

  return {
    count: list.length,
    totalInherent,
    totalResidual,
    // Portfolio-level reduction weights by exposure, rather than averaging
    // per-risk percentages (which would let a trivial risk outvote a critical one).
    portfolioEffectiveness: controlEffectiveness(totalInherent, totalResidual),
    avgEffectiveness: measurable.length
      ? measurable.reduce((s, r) => s + r.effectiveness, 0) / measurable.length
      : null,
    breaches: list.filter(r => r.breach),
    appetite,
    issues: auditRisks(risks)
  }
}
