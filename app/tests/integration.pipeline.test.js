import { describe, it, expect } from 'vitest'
import { trustScore } from '../src/logic/showcase.js'
import { createCase, advanceCase, addEvidence, verifyChain } from '../src/logic/fieldVerify.js'
import { assessCampaign, dueDiligence } from '../src/logic/riskLegal.js'
import { evaluateTerms } from '../src/logic/negotiation.js'
import { dealReadiness } from '../src/logic/pipeline.js'

// Spec 19 — feed REAL domain outputs into the pipeline. No synthetic
// shapes: the whole point is to catch output-contract drift that unit
// tests (each domain alone) cannot see.

const PLAYBOOK = { rules: [
  { term: 'discount', op: 'max', value: 20, severity: 'block' },
  { term: 'liability', op: 'required', value: 'capped-1x', severity: 'block' }
] }

// Walk a field case through the real state machine to `attested`.
function attestedCase(now = 1_000) {
  const k = createCase({ id: 'FV', country: 'JP', subject: 'audit' })
  advanceCase(k, 'assigned', now)
  advanceCase(k, 'on-site', now)
  addEvidence(k, { type: 'site-photo', ref: 'p1' }, now)
  addEvidence(k, { type: 'license-scan', ref: 'l1' }, now)
  advanceCase(k, 'evidence-collected', now)
  advanceCase(k, 'report-drafted', now)
  advanceCase(k, 'attested', now)
  return k
}

// The canonical component wiring (TrustPipeline.vue): verifyChain→chainValid.
const asFieldCase = k => ({ state: k.state, chainValid: verifyChain(k).valid })

describe('all-green scenario built from real domain outputs', () => {
  it('composes to 100 / ready / readyToSign', () => {
    const reels = [
      trustScore({ provenance: true, metricsVerified: true, clientAttested: true, complianceGate: true }),
      trustScore({ provenance: true, metricsVerified: true, clientAttested: true, complianceGate: true })
    ]
    const k = attestedCase()
    const compliance = assessCampaign({ markets: ['JP', 'EU'], attributes: {
      consent: true, dpa: true, localization: true, ageGate: true, adDisclosure: true, provenance: true
    } })
    const diligence = dueDiligence({ checks: {
      kyb: true, sanctions: true, references: true, financials: true, dataProcessing: true
    } })
    const terms = evaluateTerms({ discount: 10, liability: 'capped-1x' }, PLAYBOOK)

    // sanity: the real case really reached attested with an intact chain
    expect(k.state).toBe('attested')
    expect(verifyChain(k).valid).toBe(true)

    const r = dealReadiness({ reels, fieldCase: asFieldCase(k), compliance, diligence, terms })
    expect(r.score).toBe(100)
    expect(r.stage).toBe('ready')
    expect(r.readyToSign).toBe(true)
    expect(r.hardFail).toBe(false)
  })
})

describe('real hard-fails propagate through the pipeline', () => {
  const greenReels = [trustScore({ provenance: true, metricsVerified: true, clientAttested: true, complianceGate: true })]
  const greenTerms = evaluateTerms({ discount: 10, liability: 'capped-1x' }, PLAYBOOK)
  const greenCompliance = assessCampaign({ markets: ['JP'], attributes: { consent: true, localization: true } })

  it('a real sanctions gap (dueDiligence gate=block) caps the deal', () => {
    const diligence = dueDiligence({ checks: { kyb: true, references: true, financials: true, dataProcessing: true } })
    expect(diligence.gate).toBe('block') // produced by the real engine, not asserted by hand

    const r = dealReadiness({
      reels: greenReels, fieldCase: asFieldCase(attestedCase()),
      compliance: greenCompliance, diligence, terms: greenTerms
    })
    expect(r.hardFail).toBe(true)
    expect(r.readyToSign).toBe(false)
    expect(r.score).toBeLessThanOrEqual(40)
  })

  it('a real tampered evidence chain (verifyChain valid=false) hard-fails', () => {
    const k = attestedCase()
    k.evidence[0].ref = 'edited-after-the-fact.bin' // tamper after sealing
    expect(verifyChain(k).valid).toBe(false)         // real engine detects it

    const diligence = dueDiligence({ checks: { kyb: true, sanctions: true, references: true, financials: true, dataProcessing: true } })
    const r = dealReadiness({
      reels: greenReels, fieldCase: asFieldCase(k),
      compliance: greenCompliance, diligence, terms: greenTerms
    })
    expect(r.hardFail).toBe(true)
    expect(r.score).toBeLessThanOrEqual(40)
  })
})

describe('field contracts the pipeline depends on', () => {
  it('trustScore emits a numeric score', () => {
    expect(typeof trustScore({ provenance: true }).score).toBe('number')
  })

  it('assessCampaign / dueDiligence emit a gate in {pass,review,block}', () => {
    const g1 = assessCampaign({ markets: ['JP'], attributes: { consent: true, localization: true } }).gate
    const g2 = dueDiligence({ checks: { kyb: true, sanctions: true } }).gate
    expect(['pass', 'review', 'block']).toContain(g1)
    expect(['pass', 'review', 'block']).toContain(g2)
  })

  it('evaluateTerms emits a verdict in {accept,counter,reject}', () => {
    const v = evaluateTerms({ discount: 10, liability: 'capped-1x' }, PLAYBOOK).verdict
    expect(['accept', 'counter', 'reject']).toContain(v)
  })

  it('verifyChain emits a boolean valid (adapted to chainValid)', () => {
    expect(typeof verifyChain(attestedCase()).valid).toBe('boolean')
  })
})
