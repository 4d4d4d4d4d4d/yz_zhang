import { describe, it, expect } from 'vitest'
import { normalCdf, proportionZTest, recommendation } from '../src/logic/significance.js'

describe('normalCdf', () => {
  it('anchors at the known values', () => {
    expect(normalCdf(0)).toBeCloseTo(0.5, 5)
    expect(normalCdf(1.96)).toBeCloseTo(0.975, 3)
    expect(normalCdf(-1.96)).toBeCloseTo(0.025, 3)
  })
})

describe('proportionZTest', () => {
  it('flags a real winner as significant', () => {
    // 10% vs 13% at n=1000 each → z≈2.1, p≈0.035
    const r = proportionZTest({ convA: 100, nA: 1000, convB: 130, nB: 1000 })
    expect(r.valid).toBe(true)
    expect(r.rateA).toBeCloseTo(0.10, 5)
    expect(r.rateB).toBeCloseTo(0.13, 5)
    expect(r.lift).toBeCloseTo(0.30, 2)
    expect(r.pValue).toBeGreaterThan(0.02)
    expect(r.pValue).toBeLessThan(0.05)
    expect(r.significant).toBe(true)
    expect(r.z).toBeGreaterThan(0)
  })

  it('does not call a tiny difference significant', () => {
    const r = proportionZTest({ convA: 100, nA: 1000, convB: 105, nB: 1000 })
    expect(r.significant).toBe(false)
    expect(r.pValue).toBeGreaterThan(0.05)
  })

  it('a bigger sample shrinks the p-value for the same rates', () => {
    const small = proportionZTest({ convA: 100, nA: 1000, convB: 120, nB: 1000 })
    const big = proportionZTest({ convA: 1000, nA: 10000, convB: 1200, nB: 10000 })
    expect(big.pValue).toBeLessThan(small.pValue)
  })

  it('handles zero conversions without NaN', () => {
    const r = proportionZTest({ convA: 0, nA: 1000, convB: 0, nB: 1000 })
    expect(r.z).toBe(0)
    expect(r.pValue).toBeCloseTo(1, 5)
    expect(r.significant).toBe(false)
  })

  it('is invalid without visitors', () => {
    expect(proportionZTest({ convA: 1, nA: 0, convB: 1, nB: 10 })).toEqual({ valid: false })
    expect(proportionZTest()).toEqual({ valid: false })
  })
})

describe('recommendation', () => {
  it('ships a significant positive lift', () => {
    expect(recommendation(proportionZTest({ convA: 100, nA: 1000, convB: 150, nB: 1000 }))).toBe('ship')
  })
  it('recommends rollback on a significant negative lift', () => {
    expect(recommendation(proportionZTest({ convA: 150, nA: 1000, convB: 100, nB: 1000 }))).toBe('rollback')
  })
  it('keeps testing when not significant', () => {
    expect(recommendation(proportionZTest({ convA: 100, nA: 1000, convB: 103, nB: 1000 }))).toBe('keep_testing')
  })
  it('is invalid for a bad result', () => {
    expect(recommendation({ valid: false })).toBe('invalid')
    expect(recommendation(null)).toBe('invalid')
  })
})
