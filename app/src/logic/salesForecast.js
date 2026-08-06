// Spec 47 — sales forecasting. Pure. Forecast categories (commit / best /
// upside) are a PARTITION of the pipeline: a Closed Won deal already sits in
// commit, so committed revenue must never be re-added to it (that double count
// is the bug this module was extracted to kill). Adds pipeline coverage — the
// ratio every sales org runs on and which the inline version lacked entirely.

// Ordered low→high along the funnel ladder; weight = win probability.
export const DEFAULT_STAGES = [
  { name: 'Lead',        weight: 0.10 },
  { name: 'Discovery',   weight: 0.25 },
  { name: 'Proposal',    weight: 0.55 },
  { name: 'Negotiation', weight: 0.65 },
  { name: 'Verbal',      weight: 0.85 },
  { name: 'Closed Won',  weight: 1.00 }
]

export const CATEGORIES = ['commit', 'best', 'upside']
export const COVERAGE_BENCHMARK = 3 // the industry "3x pipeline" rule

const list = d => (Array.isArray(d) ? d : [])
const val = d => Number(d?.value) || 0

export function stageWeight(stageName, stages = DEFAULT_STAGES) {
  return stages.find(s => s.name === stageName)?.weight ?? 0
}

// Probability-weighted pipeline across every deal.
export function weightedPipeline(deals, stages = DEFAULT_STAGES) {
  return list(deals).reduce((s, d) => s + val(d) * stageWeight(d?.stage, stages), 0)
}

// Mutually exclusive category totals. Unknown categories are ignored rather
// than silently folded into a bucket they don't belong to.
export function categoryTotals(deals) {
  const out = { commit: 0, best: 0, upside: 0 }
  for (const d of list(deals)) {
    if (CATEGORIES.includes(d?.category)) out[d.category] += val(d)
  }
  return out
}

export function closedWonTotal(deals) {
  return list(deals).filter(d => d?.stage === 'Closed Won').reduce((s, d) => s + val(d), 0)
}

// Still-open pipeline — what can actually be worked to close the gap.
export function openPipeline(deals) {
  return list(deals).filter(d => d?.stage !== 'Closed Won').reduce((s, d) => s + val(d), 0)
}

// Coverage = open pipeline ÷ remaining gap. Null when the gap is already
// closed (coverage is meaningless, not infinite, once quota is met).
export function coverageRatio(open, gap) {
  return gap > 0 ? open / gap : null
}

// Forecast hygiene: a Closed Won deal that is not in commit breaks the
// partition and will misstate the roll-up. Surfaced, not silently corrected.
export function auditCategories(deals) {
  return list(deals)
    .filter(d => d?.stage === 'Closed Won' && d?.category !== 'commit')
    .map(d => ({ id: d.id, issue: 'closed-won-not-commit' }))
}

export function forecastSummary({ deals, quota = 0, stages = DEFAULT_STAGES } = {}) {
  const cats = categoryTotals(deals)
  const closedWon = closedWonTotal(deals)
  const open = openPipeline(deals)

  // Committed = the commit category, which already contains Closed Won.
  const committed = cats.commit
  const bestCase = committed + cats.best
  const allIn = bestCase + cats.upside
  const q = Number(quota) || 0
  const gap = Math.max(0, q - committed)

  return {
    quota: q,
    closedWon,
    commit: cats.commit,
    best: cats.best,
    upside: cats.upside,
    committed,
    bestCase,
    allIn,
    weighted: weightedPipeline(deals, stages),
    openPipeline: open,
    attainment: q > 0 ? (committed / q) * 100 : 0,
    gap,
    coverage: coverageRatio(open, gap),
    coverageHealthy: (coverageRatio(open, gap) ?? Infinity) >= COVERAGE_BENCHMARK,
    issues: auditCategories(deals)
  }
}
