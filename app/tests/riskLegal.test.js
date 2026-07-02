import { describe, it, expect } from 'vitest'
import { assessCampaign, dueDiligence } from '../src/logic/riskLegal.js'

const ALL_OK = { consent: true, dpa: true, localization: true, ageGate: true, adDisclosure: true, provenance: true }

describe('assessCampaign', () => {
  it('passes when every requirement is met', () => {
    const r = assessCampaign({ markets: ['EU', 'JP', 'US'], attributes: ALL_OK })
    expect(r.gate).toBe('pass')
    expect(r.riskScore).toBe(0)
  })

  it('missing consent blocks (gate precedence over warns)', () => {
    const r = assessCampaign({ markets: ['EU'], attributes: { ...ALL_OK, consent: false, ageGate: false } })
    expect(r.gate).toBe('block')
    expect(r.findings.some(f => f.key === 'consent' && f.severity === 'block')).toBe(true)
  })

  it('only warn-level gaps gate to review', () => {
    const r = assessCampaign({ markets: ['EU'], attributes: { ...ALL_OK, ageGate: false } })
    expect(r.gate).toBe('review')
  })

  it('deduplicates shared requirements across markets and regimes', () => {
    // consent is demanded by EU/GDPR, JP/APPI, CN/PIPL — must appear once.
    const r = assessCampaign({ markets: ['EU', 'JP', 'CN'], attributes: { ...ALL_OK, consent: false } })
    expect(r.findings.filter(f => f.key === 'consent')).toHaveLength(1)
    expect(r.findings[0].sources.length).toBeGreaterThan(1)
  })

  it('fails closed on unknown markets', () => {
    const r = assessCampaign({ markets: ['MARS'], attributes: ALL_OK })
    expect(r.gate).toBe('review')
    expect(r.findings[0].key).toBe('unknown-market')
  })

  it('caps risk score at 100', () => {
    // 6 deduped unmet requirements (2 blocks + 4 warns = 90) + 2 unknown-market warns = 110 → capped
    const r = assessCampaign({ markets: ['EU', 'US', 'JP', 'KR', 'CN', 'BR', 'SG', 'UK', 'MARS', 'VENUS'], attributes: {} })
    expect(r.riskScore).toBe(100)
    expect(r.gate).toBe('block')
  })
})

describe('dueDiligence', () => {
  it('clean checklist passes', () => {
    const r = dueDiligence({ checks: { kyb: true, sanctions: true, references: true, financials: true, dataProcessing: true } })
    expect(r.gate).toBe('pass')
  })

  it('missing sanctions blocks even when all else is complete', () => {
    const r = dueDiligence({ checks: { kyb: true, references: true, financials: true, dataProcessing: true } })
    expect(r.gate).toBe('block')
    expect(r.findings.map(f => f.key)).toEqual(['sanctions'])
  })

  it('soft gaps only → review', () => {
    const r = dueDiligence({ checks: { kyb: true, sanctions: true } })
    expect(r.gate).toBe('review')
  })
})
