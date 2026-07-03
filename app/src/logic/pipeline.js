// Spec 11 — trust pipeline: compose domain outputs into deal readiness.
// Consumes results from showcase/fieldVerify/riskLegal/negotiation —
// never imports those modules (spec 00 §2: no cross-domain imports).

export const STAGES = ['evidence', 'verification', 'compliance', 'commercial']

const POINTS = 25

const ACTIONS = {
  evidence: {
    zero: 'Link at least one showcase reel to this deal',
    half: 'Raise reel quality — collect verified metrics or a client attestation to lift avg trust ≥ 60'
  },
  verification: {
    zero: 'Commission a field investigation — no on-site evidence yet',
    half: 'Investigation under way — evidence collected, awaiting attested report'
  },
  compliance: {
    zero: 'Hard compliance block — resolve blocking findings (consent/DPA/sanctions) before anything else',
    half: 'Compliance in review — clear the warn-level findings'
  },
  commercial: {
    zero: 'Terms rejected — restructure the proposal against the playbook',
    half: 'Counter-proposal pending — resolve warn-level terms'
  }
}

function gateEvidence(reels) {
  if (!Array.isArray(reels) || reels.length === 0) return 0
  const avg = reels.reduce((s, r) => s + (Number(r?.score) || 0), 0) / reels.length
  return avg >= 60 ? 1 : 0.5
}

function gateVerification(fieldCase) {
  if (!fieldCase) return 0
  const state = fieldCase.state
  const attested = state === 'attested' || state === 'closed'
  if (attested && fieldCase.chainValid) return 1
  const progressed = ['evidence-collected', 'report-drafted', 'attested', 'closed'].includes(state)
  return progressed && fieldCase.chainValid !== false ? 0.5 : 0
}

function gateCompliance(compliance, diligence) {
  const gates = [compliance?.gate, diligence?.gate]
  if (gates.some(g => g === 'block')) return 0
  if (gates.every(g => g === 'pass')) return 1
  if (gates.every(g => g === 'pass' || g === 'review')) return 0.5
  return 0 // missing gate = not assessed = no credit
}

function gateCommercial(terms) {
  if (terms?.verdict === 'accept') return 1
  if (terms?.verdict === 'counter') return 0.5
  return 0
}

export function dealReadiness({ reels, fieldCase, compliance, diligence, terms } = {}) {
  const credits = {
    evidence: gateEvidence(reels),
    verification: gateVerification(fieldCase),
    compliance: gateCompliance(compliance, diligence),
    commercial: gateCommercial(terms)
  }

  let score = STAGES.reduce((s, st) => s + credits[st] * POINTS, 0)

  // Hard-fail override: a compliance block or a broken evidence chain
  // caps the deal — you cannot out-market a sanctions hit.
  const hardFail =
    compliance?.gate === 'block' ||
    diligence?.gate === 'block' ||
    fieldCase?.chainValid === false
  if (hardFail) score = Math.min(score, 40)

  const stage = STAGES.find(st => credits[st] < 1) || 'ready'
  const readyToSign = stage === 'ready' && !hardFail

  const blockers = STAGES
    .filter(st => credits[st] < 1)
    .map(st => ({
      stage: st,
      severity: credits[st] === 0 ? 'zero' : 'half',
      action: ACTIONS[st][credits[st] === 0 ? 'zero' : 'half']
    }))

  return { score: Math.round(score), stage, readyToSign, hardFail, credits, blockers }
}
