// Spec 60 — market go-live readiness. Pure; `now` injected.
//
// The distinction that makes this useful is blocking vs advisory. A percentage
// that averages "VAT registration filed" together with "help-centre translated"
// produces a comfortable 85% next to a market that legally cannot transact.
// So a blocking gate does not reduce the score — it withholds the go-live
// entirely, and is reported by name.

export const GATE_KINDS = { blocking: 'blocking', advisory: 'advisory' }

const DAY = 86400000
const num = n => (Number.isFinite(Number(n)) ? Number(n) : 0)
const round1 = n => Math.round(n * 10) / 10

const isDone = g => g?.status === 'done'
const weightOf = g => Math.max(0, num(g?.weight ?? 1))

export function readiness(gates = [], now = Date.now()) {
  const list = Array.isArray(gates) ? gates : []
  const blocking = list.filter(g => g?.kind === GATE_KINDS.blocking)
  const advisory = list.filter(g => g?.kind !== GATE_KINDS.blocking)

  const openBlockers = blocking.filter(g => !isDone(g))
  const advWeight = advisory.reduce((s, g) => s + weightOf(g), 0)
  const advDone = advisory.filter(isDone).reduce((s, g) => s + weightOf(g), 0)

  // Remaining calendar time is the longest pole, not the sum: remediation runs
  // in parallel across different owners.
  const remaining = list.filter(g => !isDone(g))
  const longest = remaining.reduce((max, g) => Math.max(max, num(g?.etaDays)), 0)
  const earliest = remaining.length ? now + longest * DAY : now

  return {
    canGoLive: openBlockers.length === 0,
    blockers: openBlockers.map(g => g.key),
    // Advisory completeness, reported honestly as its own number rather than
    // blended with the blocking gates it cannot substitute for.
    advisoryPct: advWeight > 0 ? round1((advDone / advWeight) * 100) : 100,
    blockingPct: blocking.length ? round1(((blocking.length - openBlockers.length) / blocking.length) * 100) : 100,
    openCount: remaining.length,
    criticalPathDays: longest,
    earliestGoLive: earliest,
    owner: remaining.reduce((worst, g) => (num(g?.etaDays) > num(worst?.etaDays) ? g : worst), null)?.owner ?? null
  }
}

// Rank markets by how close they are to transacting. A market that cannot go
// live sorts below every market that can, regardless of how polished it is.
export function readinessRank(markets = [], now = Date.now()) {
  return markets
    .map(m => ({ code: m?.code, name: m?.name, ...readiness(m?.gates, now) }))
    .sort((a, b) =>
      Number(b.canGoLive) - Number(a.canGoLive) ||
      a.criticalPathDays - b.criticalPathDays ||
      b.advisoryPct - a.advisoryPct ||
      String(a.code).localeCompare(String(b.code)))
}
