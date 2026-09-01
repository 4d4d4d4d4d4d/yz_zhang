// Spec 10 — field verification: specialist matching, case state machine,
// tamper-evident evidence chain.

const WEIGHTS = { language: 0.30, expertise: 0.40, availability: 0.30 }

function overlapRatio(want = [], have = []) {
  if (!want.length) return 0
  const H = new Set(have)
  return want.filter(w => H.has(w)).length / want.length
}

function availabilityCredit(availableInDays, urgencyDays) {
  if (availableInDays <= urgencyDays) return 1
  if (availableInDays <= urgencyDays * 2) return 0.5
  return 0
}

// Country coverage is a hard filter: on-site work needs someone there.
export function matchSpecialists(request, specialists = []) {
  const covered = specialists.filter(s =>
    s.country === request.country || (s.crossBorder || []).includes(request.country))
  return covered
    .map(s => {
      const factors = {
        language: overlapRatio(request.languages, s.languages),
        expertise: overlapRatio(request.expertise, s.expertise),
        availability: availabilityCredit(s.availableInDays ?? Infinity, request.urgencyDays ?? 7)
      }
      const score = Math.round(
        Object.entries(WEIGHTS).reduce((acc, [k, w]) => acc + w * factors[k], 0) * 100)
      return { specialist: s, score, factors }
    })
    .sort((a, b) => b.score - a.score
      || (b.specialist.rating || 0) - (a.specialist.rating || 0)
      || String(a.specialist.id).localeCompare(String(b.specialist.id)))
}

// ------------------------------------------------------------ case workflow

export const CASE_STATES = [
  'requested', 'assigned', 'on-site', 'evidence-collected',
  'report-drafted', 'attested', 'closed'
]

export function createCase({ id, country, subject } = {}) {
  return { id, country, subject, state: 'requested', evidence: [], audit: [] }
}

export function advanceCase(kase, toState, now = Date.now()) {
  const fromIdx = CASE_STATES.indexOf(kase.state)
  const toIdx = CASE_STATES.indexOf(toState)
  if (toIdx === -1) return { ok: false, reason: `unknown state "${toState}"` }
  if (toIdx !== fromIdx + 1) {
    return { ok: false, reason: `illegal transition ${kase.state} → ${toState} (no skips, no regressions)` }
  }
  if (toState === 'attested') {
    if (!kase.evidence.length) return { ok: false, reason: 'attestation requires evidence' }
    const chain = verifyChain(kase)
    if (!chain.valid) return { ok: false, reason: `evidence chain broken at #${chain.brokenAt}` }
  }
  kase.audit.push({ at: now, from: kase.state, to: toState })
  kase.state = toState
  return { ok: true }
}

// ------------------------------------------------------- evidence chain

// djb2-style demo hash — tamper-evidence for the demo ledger, not crypto.
export function demoHash(input) {
  let h = 5381
  const s = String(input)
  for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0
  return h.toString(16).padStart(8, '0')
}

export function addEvidence(kase, { type, ref }, now = Date.now()) {
  const prevHash = kase.evidence.length ? kase.evidence[kase.evidence.length - 1].hash : 'genesis'
  const item = { seq: kase.evidence.length, type, ref, at: now, prevHash }
  item.hash = demoHash(prevHash + type + ref + now)
  kase.evidence.push(item)
  return item
}

export function verifyChain(kase) {
  let prevHash = 'genesis'
  for (let i = 0; i < kase.evidence.length; i++) {
    const e = kase.evidence[i]
    if (e.prevHash !== prevHash || e.hash !== demoHash(prevHash + e.type + e.ref + e.at)) {
      return { valid: false, brokenAt: i }
    }
    prevHash = e.hash
  }
  return { valid: true, brokenAt: null }
}
