import { describe, it, expect } from 'vitest'
import {
  riskScore, severityBand, controlEffectiveness, exceedsAppetite,
  auditRisks, assessRisk, portfolioRisk, DEFAULT_APPETITE, MAX_SCORE
} from '../src/logic/risk.js'

const RISK = { id: 'R-001', i: { l: 4, p: 5 }, r: { l: 2, p: 5 } } // 20 → 10

describe('riskScore', () => {
  it('multiplies likelihood by impact', () => {
    expect(riskScore(4, 5)).toBe(20)
    expect(riskScore(1, 1)).toBe(1)
    expect(riskScore(5, 5)).toBe(MAX_SCORE)
  })
  it('clamps to the 0..5 scale and guards junk', () => {
    expect(riskScore(99, 5)).toBe(MAX_SCORE)
    expect(riskScore(-3, 5)).toBe(0)
    expect(riskScore('x', 5)).toBe(0)
    expect(riskScore()).toBe(0)
  })
})

describe('severityBand', () => {
  it('bands the matrix', () => {
    expect(severityBand(20)).toBe('critical')
    expect(severityBand(16)).toBe('critical')
    expect(severityBand(15)).toBe('high')
    expect(severityBand(12)).toBe('high')
    expect(severityBand(11)).toBe('med')
    expect(severityBand(6)).toBe('med')
    expect(severityBand(5)).toBe('low')
    expect(severityBand(0)).toBe('low')
  })
})

describe('controlEffectiveness', () => {
  it('is the fraction of inherent risk removed', () => {
    expect(controlEffectiveness(20, 10)).toBeCloseTo(0.5, 6)
    expect(controlEffectiveness(20, 0)).toBe(1)
    expect(controlEffectiveness(20, 20)).toBe(0)
  })
  it('is null when there is no inherent risk to reduce', () => {
    expect(controlEffectiveness(0, 0)).toBeNull()
  })
  it('never reports negative effectiveness', () => {
    expect(controlEffectiveness(10, 25)).toBe(0)
  })
})

describe('exceedsAppetite', () => {
  it('breaches strictly above the threshold', () => {
    expect(exceedsAppetite(9, 8)).toBe(true)
    expect(exceedsAppetite(8, 8)).toBe(false) // equal is within tolerance
    expect(exceedsAppetite(7, 8)).toBe(false)
  })
  it('defaults to the standard appetite', () => {
    expect(exceedsAppetite(DEFAULT_APPETITE + 1)).toBe(true)
  })
})

describe('assessRisk', () => {
  it('reports both bands, effectiveness and breach', () => {
    const a = assessRisk(RISK)
    expect(a.inherent).toBe(20)
    expect(a.residual).toBe(10)
    expect(a.inherentBand).toBe('critical')
    expect(a.residualBand).toBe('med')
    expect(a.effectiveness).toBeCloseTo(0.5, 6)
    expect(a.breach).toBe(true) // 10 > appetite 8
  })
  it('handles a malformed entry without throwing', () => {
    const a = assessRisk({})
    expect(a.inherent).toBe(0)
    expect(a.effectiveness).toBeNull()
    expect(a.breach).toBe(false)
  })
})

describe('auditRisks', () => {
  it('flags a residual above its inherent — controls cannot raise risk', () => {
    expect(auditRisks([{ id: 'BAD', i: { l: 1, p: 1 }, r: { l: 5, p: 5 } }]))
      .toEqual([{ id: 'BAD', issue: 'residual-exceeds-inherent' }])
  })
  it('is clean for a well-formed register', () => {
    expect(auditRisks([RISK])).toEqual([])
    expect(auditRisks(null)).toEqual([])
  })
})

describe('portfolioRisk', () => {
  const REGISTER = [
    { id: 'A', i: { l: 4, p: 5 }, r: { l: 2, p: 5 } }, // 20 → 10, breach
    { id: 'B', i: { l: 2, p: 2 }, r: { l: 1, p: 2 } }, // 4 → 2, ok
    { id: 'C', i: { l: 3, p: 5 }, r: { l: 1, p: 4 } }  // 15 → 4, ok
  ]

  it('totals exposure and lists appetite breaches', () => {
    const p = portfolioRisk(REGISTER)
    expect(p.count).toBe(3)
    expect(p.totalInherent).toBe(39)
    expect(p.totalResidual).toBe(16)
    expect(p.breaches.map(b => b.id)).toEqual(['A'])
    expect(p.appetite).toBe(DEFAULT_APPETITE)
  })

  it('weights portfolio effectiveness by exposure', () => {
    const p = portfolioRisk(REGISTER)
    expect(p.portfolioEffectiveness).toBeCloseTo((39 - 16) / 39, 6)
  })

  it('does not let a trivial fully-controlled risk mask an uncontrolled critical one', () => {
    // Tiny risk fully mitigated (1 → 0); critical risk untouched (25 → 25).
    // The plain average says 50% controlled; the exposure-weighted truth is 4%.
    const p = portfolioRisk([
      { id: 'tiny', i: { l: 1, p: 1 }, r: { l: 0, p: 0 } },
      { id: 'critical', i: { l: 5, p: 5 }, r: { l: 5, p: 5 } }
    ])
    expect(p.avgEffectiveness).toBeCloseTo(0.5, 6)
    expect(p.portfolioEffectiveness).toBeCloseTo(1 / 26, 6)
    expect(p.portfolioEffectiveness).toBeLessThan(p.avgEffectiveness)
  })

  it('honours a custom appetite', () => {
    expect(portfolioRisk(REGISTER, { appetite: 20 }).breaches).toEqual([])
    expect(portfolioRisk(REGISTER, { appetite: 1 }).breaches).toHaveLength(3)
  })

  it('guards an empty register', () => {
    const p = portfolioRisk([])
    expect(p.count).toBe(0)
    expect(p.portfolioEffectiveness).toBeNull()
    expect(p.avgEffectiveness).toBeNull()
    expect(p.breaches).toEqual([])
  })
})
