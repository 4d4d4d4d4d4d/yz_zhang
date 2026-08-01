// Spec 42 — Data Subject Requests (GDPR/CCPA/LGPD/APPI Art. 15–22). Pure:
// statutory response windows, due-date math, and status derived from `now`.
// The regime — not a hardcoded date — determines the deadline.

// Statutory response windows in calendar days.
export const REGIME_DAYS = { GDPR: 30, UKGDPR: 30, CCPA: 45, LGPD: 15, APPI: 14, PIPL: 15 }

// Canonical request rights.
export const REQUEST_TYPES = ['access', 'erasure', 'portability', 'rectification', 'objection']

const DAY = 86400000
const DUE_SOON_DAYS = 7

export function regimeDays(regime) {
  return REGIME_DAYS[regime] ?? 30 // unknown regime → GDPR-equivalent, the strictest common default
}

export function dueAt(regime, receivedAt) {
  return receivedAt + regimeDays(regime) * DAY
}

export function createDSR({ id, type, regime, subject, receivedAt, resolution = null } = {}, now = Date.now()) {
  const at = Number.isFinite(receivedAt) ? receivedAt : now
  return { id, type, regime, subject, receivedAt: at, dueAt: dueAt(regime, at), resolution }
}

// Derived status: a resolved request keeps its resolution; otherwise it is
// overdue past the deadline, due_soon within the window, else open.
export function dsrStatus(req, now = Date.now()) {
  if (req?.resolution === 'fulfilled' || req?.resolution === 'rejected') return req.resolution
  if (now >= req.dueAt) return 'overdue'
  if (req.dueAt - now <= DUE_SOON_DAYS * DAY) return 'due_soon'
  return 'open'
}

// Whole hours until the deadline (0 once overdue).
export function hoursRemaining(req, now = Date.now()) {
  return Math.max(0, Math.round((req.dueAt - now) / 3600000))
}

export function summarizeDSR(reqs = [], now = Date.now()) {
  const out = { total: 0, open: 0, due_soon: 0, overdue: 0, resolved: 0 }
  for (const r of Array.isArray(reqs) ? reqs : []) {
    out.total++
    const s = dsrStatus(r, now)
    if (s === 'fulfilled' || s === 'rejected') out.resolved++
    else out[s]++
  }
  return out
}
