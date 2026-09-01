import { describe, it, expect } from 'vitest'
import { buildDealReport, reportVerdict } from '../src/logic/dealReport.js'
import { dealReadiness } from '../src/logic/pipeline.js'

// A fully-clean deal that the pipeline scores as ready.
const READY = {
  reels: [{ score: 85 }],
  fieldCase: { state: 'attested', chainValid: true },
  compliance: { gate: 'pass' },
  diligence: { gate: 'pass' },
  terms: { verdict: 'accept' }
}

describe('reportVerdict', () => {
  it('is blocked on a hard fail regardless of score', () => {
    expect(reportVerdict({ hardFail: true, readyToSign: false, score: 40 })).toBe('blocked')
  })
  it('is ready only when the pipeline says so', () => {
    expect(reportVerdict({ hardFail: false, readyToSign: true })).toBe('ready')
  })
  it('is in progress otherwise', () => {
    expect(reportVerdict({ hardFail: false, readyToSign: false })).toBe('progress')
  })
})

describe('buildDealReport', () => {
  it('summarizes a ready deal: verdict ready, all stages complete', () => {
    const r = buildDealReport(dealReadiness(READY), { now: 1000, id: 'ACME' })
    expect(r.id).toBe('ACME')
    expect(r.verdict).toBe('ready')
    expect(r.score).toBe(100)
    expect(r.total).toBe(4)
    expect(r.complete).toBe(4)
    expect(r.blockers).toEqual([])
    expect(r.generatedAt).toBe(1000)
    expect(r.stages.every(s => s.status === 'complete')).toBe(true)
  })

  it('maps credits to complete/partial/open', () => {
    const readiness = dealReadiness({
      ...READY,
      terms: { verdict: 'counter' },     // 0.5 → partial
      compliance: { gate: 'block' }      // 0 → open + hard fail
    })
    const r = buildDealReport(readiness)
    const byStage = Object.fromEntries(r.stages.map(s => [s.stage, s.status]))
    expect(byStage.commercial).toBe('partial')
    expect(byStage.compliance).toBe('open')
    expect(r.verdict).toBe('blocked')
  })

  it('orders blockers with hard (zero) severity before soft (half)', () => {
    const readiness = dealReadiness({
      reels: [{ score: 70 }],            // 1 complete
      fieldCase: { state: 'evidence-collected', chainValid: true }, // 0.5 half
      compliance: { gate: 'pass' },
      diligence: { gate: 'pass' },
      terms: { verdict: 'reject' }       // 0 zero
    })
    const r = buildDealReport(readiness)
    expect(r.blockers.length).toBeGreaterThanOrEqual(2)
    expect(r.blockers[0].severity).toBe('zero')
    // zeros come before halves
    const severities = r.blockers.map(b => b.severity)
    const firstHalf = severities.indexOf('half')
    const lastZero = severities.lastIndexOf('zero')
    expect(lastZero).toBeLessThan(firstHalf)
  })

  it('is defensive against a missing/empty readiness', () => {
    const r = buildDealReport(undefined)
    expect(r.verdict).toBe('progress')
    expect(r.score).toBe(0)
    expect(r.stages).toEqual([])
    expect(r.total).toBe(0)
    expect(r.blockers).toEqual([])
  })
})
