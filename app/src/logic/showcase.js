// Spec 06 — digital video showcase: trust scoring, scoped share links,
// bounded-concurrency verification queue.

export const TRUST_WEIGHTS = {
  provenance: 35,       // C2PA credential present, chain intact
  metricsVerified: 25,  // numbers pulled from platform APIs
  clientAttested: 20,   // counterparty signed the case study
  complianceGate: 20    // spec-05 gate === pass
}

export function trustScore(reel = {}) {
  const evidence = Object.keys(TRUST_WEIGHTS).map(key => ({
    key,
    present: Boolean(reel[key]),
    weight: TRUST_WEIGHTS[key]
  }))
  const score = evidence.reduce((s, e) => s + (e.present ? e.weight : 0), 0)
  const badge = score >= 85 ? 'verified' : score >= 60 ? 'substantiated' : 'claimed'
  return { score, badge, evidence }
}

// ---------------------------------------------------------------- Trust Links

const TOKEN_CHARS = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
const ALL_SCOPES = ['assets', 'metrics', 'provenance', 'pricing']
export const MAX_LINK_DAYS = 90

export function generateToken(rng = Math.random, length = 24) {
  let out = ''
  for (let i = 0; i < length; i++) out += TOKEN_CHARS[Math.floor(rng() * TOKEN_CHARS.length)]
  return out
}

// Least-privilege share link. Token is an opaque id — no payload encoded.
// Raw (unwatermarked) assets never leave via link: watermark can only be
// disabled when the link does not expose assets.
export function createTrustLink({
  reelIds = [],
  scopes = ['assets', 'metrics', 'provenance'],
  expiresInDays = 7,
  watermark = true,
  now = Date.now(),
  rng = Math.random
} = {}) {
  const cleanScopes = [...new Set(scopes)].filter(s => ALL_SCOPES.includes(s))
  if (!watermark && cleanScopes.includes('assets')) {
    throw new Error('watermark cannot be disabled on links that expose assets')
  }
  const days = Math.min(MAX_LINK_DAYS, Math.max(1, Number(expiresInDays) || 7))
  return {
    token: generateToken(rng),
    reelIds: [...reelIds],
    scopes: cleanScopes,
    watermark,
    createdAt: now,
    expiresAt: now + days * 86400000,
    revoked: false
  }
}

export function validateTrustLink(link, now = Date.now()) {
  if (!link || typeof link.token !== 'string' || link.token.length < 16) {
    return { valid: false, reason: 'malformed' }
  }
  if (link.revoked) return { valid: false, reason: 'revoked' }
  if (now >= link.expiresAt) return { valid: false, reason: 'expired' }
  return { valid: true }
}

export function revokeTrustLink(link) {
  if (link) link.revoked = true
  return link
}

// --------------------------------------------------- Verification queue

// Bounded-concurrency scheduler: at most `limit` tasks in flight,
// higher priority first, FIFO within a priority class. A failing task
// releases its slot and rejects only its own caller.
export function createQueue(limit = 3) {
  if (!Number.isInteger(limit) || limit < 1) throw new Error('limit must be a positive integer')
  const waiting = []
  let seq = 0
  const stats = { inFlight: 0, queued: 0, done: 0, failed: 0 }

  function pump() {
    while (stats.inFlight < limit && waiting.length) {
      waiting.sort((a, b) => b.priority - a.priority || a.seq - b.seq)
      const job = waiting.shift()
      stats.queued--
      stats.inFlight++
      Promise.resolve()
        .then(() => job.task())
        .then(
          value => { stats.inFlight--; stats.done++; job.resolve(value); pump() },
          err => { stats.inFlight--; stats.failed++; job.reject(err); pump() }
        )
    }
  }

  return {
    enqueue(task, { priority = 1 } = {}) {
      return new Promise((resolve, reject) => {
        waiting.push({ task, priority, seq: seq++, resolve, reject })
        stats.queued++
        pump()
      })
    },
    stats: () => ({ ...stats })
  }
}
