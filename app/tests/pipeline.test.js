import { describe, it, expect } from 'vitest'
import { dealReadiness, STAGES } from '../src/logic/pipeline.js'

const GREEN = {
  reels: [{ score: 80 }, { score: 100 }],
  fieldCase: { state: 'attested', chainValid: true },
  compliance: { gate: 'pass' },
  diligence: { gate: 'pass' },
  terms: { verdict: 'accept' }
}

describe('dealReadiness — happy path', () => {
  it('all-green fixture → 100 / ready / readyToSign / no blockers', () => {
    const r = dealReadiness(GREEN)
    expect(r.score).toBe(100)
    expect(r.stage).toBe('ready')
    expect(r.readyToSign).toBe(true)
    expect(r.hardFail).toBe(false)
    expect(r.blockers).toEqual([])
  })

  it('closed case counts like attested', () => {
    expect(dealReadiness({ ...GREEN, fieldCase: { state: 'closed', chainValid: true } }).score).toBe(100)
  })
})

describe('gate credit tiers', () => {
  it('evidence: no reels → 0; low avg → half; stage stops at evidence', () => {
    const zero = dealReadiness({ ...GREEN, reels: [] })
    expect(zero.credits.evidence).toBe(0)
    expect(zero.stage).toBe('evidence')
    const half = dealReadiness({ ...GREEN, reels: [{ score: 35 }, { score: 55 }] })
    expect(half.credits.evidence).toBe(0.5)
    expect(half.score).toBe(88) // 12.5 + 75, rounded
  })

  it('verification: in-progress with evidence → half; early stage → zero', () => {
    expect(dealReadiness({ ...GREEN, fieldCase: { state: 'evidence-collected', chainValid: true } }).credits.verification).toBe(0.5)
    expect(dealReadiness({ ...GREEN, fieldCase: { state: 'on-site', chainValid: true } }).credits.verification).toBe(0)
    expect(dealReadiness({ ...GREEN, fieldCase: null }).credits.verification).toBe(0)
  })

  it('compliance: any review → half; missing gate → zero credit', () => {
    expect(dealReadiness({ ...GREEN, compliance: { gate: 'review' } }).credits.compliance).toBe(0.5)
    expect(dealReadiness({ ...GREEN, diligence: undefined }).credits.compliance).toBe(0)
  })

  it('commercial: counter → half, reject/missing → zero', () => {
    expect(dealReadiness({ ...GREEN, terms: { verdict: 'counter' } }).credits.commercial).toBe(0.5)
    expect(dealReadiness({ ...GREEN, terms: { verdict: 'reject' } }).credits.commercial).toBe(0)
    expect(dealReadiness({ ...GREEN, terms: undefined }).credits.commercial).toBe(0)
  })

  it('blockers follow stage order and carry actions', () => {
    const r = dealReadiness({ ...GREEN, reels: [], terms: { verdict: 'counter' } })
    expect(r.blockers.map(b => b.stage)).toEqual(['evidence', 'commercial'])
    expect(r.blockers[0].severity).toBe('zero')
    expect(r.blockers[0].action).toMatch(/showcase reel/)
    expect(r.blockers[1].severity).toBe('half')
  })
})

describe('hard-fail override', () => {
  it('compliance block caps score at 40 even with three full gates', () => {
    const r = dealReadiness({ ...GREEN, compliance: { gate: 'block' } })
    expect(r.score).toBeLessThanOrEqual(40)
    expect(r.hardFail).toBe(true)
    expect(r.readyToSign).toBe(false)
  })

  it('diligence block and broken chain also hard-fail', () => {
    expect(dealReadiness({ ...GREEN, diligence: { gate: 'block' } }).hardFail).toBe(true)
    const broken = dealReadiness({ ...GREEN, fieldCase: { state: 'attested', chainValid: false } })
    expect(broken.hardFail).toBe(true)
    expect(broken.score).toBeLessThanOrEqual(40)
    expect(broken.credits.verification).toBe(0)
  })
})

describe('totality & monotonicity', () => {
  it('empty input → score 0, stage evidence, 4 blockers, no throw', () => {
    const r = dealReadiness()
    expect(r.score).toBe(0)
    expect(r.stage).toBe('evidence')
    expect(r.blockers).toHaveLength(STAGES.length)
  })

  it('improving one gate never lowers the score', () => {
    const base = dealReadiness({ ...GREEN, terms: { verdict: 'counter' } })
    const better = dealReadiness(GREEN)
    expect(better.score).toBeGreaterThanOrEqual(base.score)
  })
})
