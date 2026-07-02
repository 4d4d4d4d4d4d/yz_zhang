import { describe, it, expect } from 'vitest'
import { zopa, suggestAnchor, evaluateTerms } from '../src/logic/negotiation.js'

describe('zopa', () => {
  it('computes the zone when buyer max ≥ seller min', () => {
    const z = zopa({ max: 120 }, { min: 80 })
    expect(z).toEqual({ exists: true, low: 80, high: 120, width: 40, midpoint: 100 })
  })

  it('reports no zone when reservations cross', () => {
    const z = zopa({ max: 70 }, { min: 80 })
    expect(z.exists).toBe(false)
    expect(z.width).toBe(0)
    expect(z.midpoint).toBeNull()
  })

  it('handles malformed input without throwing', () => {
    expect(zopa(null, { min: 'x' }).exists).toBe(false)
  })
})

describe('suggestAnchor', () => {
  const z = zopa({ max: 120 }, { min: 80 })

  it('seller anchors between midpoint and high, scaling with aggressiveness', () => {
    expect(suggestAnchor(z, 'seller', 1)).toBe(120)
    expect(suggestAnchor(z, 'seller', 0)).toBe(100) // never below midpoint
    const a7 = suggestAnchor(z, 'seller', 0.7)
    expect(a7).toBeGreaterThan(100)
    expect(a7).toBeLessThan(120)
  })

  it('buyer mirrors at the low end and aggressiveness clamps to [0,1]', () => {
    expect(suggestAnchor(z, 'buyer', 1)).toBe(80)
    expect(suggestAnchor(z, 'buyer', 5)).toBe(80) // clamped
    expect(suggestAnchor(z, 'buyer', -2)).toBe(100)
  })

  it('returns null without a zone', () => {
    expect(suggestAnchor(zopa({ max: 1 }, { min: 2 }), 'seller')).toBeNull()
  })
})

describe('evaluateTerms', () => {
  const playbook = {
    rules: [
      { term: 'discount', op: 'max', value: 20, severity: 'block', label: 'Max discount %' },
      { term: 'paymentDays', op: 'max', value: 60, severity: 'warn' },
      { term: 'governingLaw', op: 'oneOf', value: ['SG', 'HK', 'DE'], severity: 'warn' },
      { term: 'liability', op: 'required', value: 'capped-1x', severity: 'block' },
      { term: 'broken', severity: 'warn' } // malformed: no op
    ]
  }

  it('any block finding rejects, even among warns', () => {
    const r = evaluateTerms({ discount: 35, paymentDays: 90, liability: 'capped-1x' }, playbook)
    expect(r.verdict).toBe('reject')
    expect(r.findings.some(f => f.term === 'discount' && f.severity === 'block')).toBe(true)
  })

  it('only warns → counter, with boundary suggestions', () => {
    const r = evaluateTerms({ discount: 10, paymentDays: 90, governingLaw: 'US', liability: 'capped-1x' }, playbook)
    expect(r.verdict).toBe('counter')
    const pay = r.findings.find(f => f.term === 'paymentDays')
    expect(pay.suggestion).toBe(60)
    const law = r.findings.find(f => f.term === 'governingLaw')
    expect(law.suggestion).toBe('SG')
  })

  it('clean proposal accepts; missing required term is a finding', () => {
    expect(evaluateTerms({ discount: 10, liability: 'capped-1x' }, playbook).verdict).toBe('accept')
    const r = evaluateTerms({ discount: 10 }, playbook)
    expect(r.verdict).toBe('reject')
    expect(r.findings.find(f => f.term === 'liability').message).toMatch(/missing/)
  })

  it('malformed rules are skipped, not thrown', () => {
    const r = evaluateTerms({ discount: 10, liability: 'x' }, playbook)
    expect(r.skipped.length).toBe(1)
  })
})
