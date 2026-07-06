// Spec 16 — customer success: health scoring, churn, SLA.
// Time is injected (spec 13 rule 2) so slaStatus is deterministic.

export const HEALTH_WEIGHTS = { usage: 0.30, payment: 0.15, support: 0.15, adoption: 0.25, sentiment: 0.15 }

export function scoreHealth(signals = {}, weights = HEALTH_WEIGHTS) {
  let s = 0
  for (const k in weights) s += (Number(signals[k]) || 0) * weights[k]
  return Math.round(Math.min(100, Math.max(0, s)))
}

export function healthBand(score) {
  if (score >= 80) return 'ok'
  if (score >= 60) return 'warn'
  return 'risk'
}

export function churnProbability(score, renewalInDays) {
  const base = Math.max(0, 100 - score) / 100
  const urgency = Math.max(0, (120 - renewalInDays) / 120)
  return Math.round(Math.min(100, Math.max(0, (base * 0.7 + urgency * 0.3) * 100)))
}

export function enrichAccount(account, weights = HEALTH_WEIGHTS) {
  const score = scoreHealth(account.signals, weights)
  return { ...account, score, band: healthBand(score), churn: churnProbability(score, account.renewalIn) }
}

export function healthSummary(accounts = []) {
  const enriched = accounts.map(a => enrichAccount(a))
  const byBand = b => enriched.filter(a => a.band === b)
  return {
    total: accounts.length,
    ok: byBand('ok').length,
    warn: byBand('warn').length,
    risk: byBand('risk').length,
    mrrAtRisk: byBand('risk').reduce((s, a) => s + (a.mrr || 0), 0),
    avgScore: enriched.length ? Math.round(enriched.reduce((s, a) => s + a.score, 0) / enriched.length) : 0
  }
}

// --------------------------------------------------------------- SLA

export function slaStatus(ticket, now) {
  const dueMs = new Date(ticket.due).getTime()
  const hoursLeft = (dueMs - now) / 3600000
  const resolved = ticket.status === 'resolved'
  const pctConsumed = resolved ? 100 : Math.min(100, (1 - hoursLeft / ticket.sla) * 100)
  const breach = !resolved && hoursLeft < 0
  return { ...ticket, hoursLeft, pctConsumed, breach }
}

export function slaSummary(tickets = [], now) {
  const enriched = tickets.map(t => slaStatus(t, now))
  const rated = enriched.filter(t => typeof t.csat === 'number')
  return {
    total: tickets.length,
    active: enriched.filter(t => t.status === 'active').length,
    breached: enriched.filter(t => t.breach).length,
    resolved: enriched.filter(t => t.status === 'resolved').length,
    csat: rated.length ? Math.round((rated.reduce((s, t) => s + t.csat, 0) / rated.length) * 10) / 10 : null
  }
}
