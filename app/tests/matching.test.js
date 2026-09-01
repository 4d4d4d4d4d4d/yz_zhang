import { describe, it, expect } from 'vitest'
import { scorePartner, rankPartners } from '../src/logic/matching.js'

const need = { categories: ['beauty', 'dtc'], markets: ['JP', 'KR'], stage: 'growth' }

describe('scorePartner', () => {
  it('perfect match scores 100 and tiers strong', () => {
    const r = scorePartner(need, { categories: ['beauty', 'dtc'], markets: ['JP', 'KR'], stage: 'growth', trust: 1 })
    expect(r.score).toBe(100)
    expect(r.tier).toBe('strong')
  })

  it('disjoint partner tiers weak', () => {
    const r = scorePartner(need, { categories: ['industrial'], markets: ['BR'], stage: 'enterprise', trust: 0 })
    expect(r.score).toBe(0)
    expect(r.tier).toBe('weak')
  })

  it('adjacent stage gives half credit; adjacent market gives 0.5 per target', () => {
    const stageAdj = scorePartner(need, { categories: [], markets: [], stage: 'scale', trust: 0 })
    expect(stageAdj.factors.stage).toBe(0.5)
    const mktAdj = scorePartner(need,
      { categories: [], markets: ['TW'], stage: 'seed', trust: 0 },
      { adjacency: { JP: ['TW'], KR: [] } })
    expect(mktAdj.factors.market).toBe(0.25) // one of two targets, half credit
  })

  it('never throws on missing fields', () => {
    expect(() => scorePartner({}, {})).not.toThrow()
  })

  it('produces human-readable reasons', () => {
    const r = scorePartner(need, { categories: ['beauty'], markets: ['JP'], stage: 'growth', trust: 0.9, verified: true })
    expect(r.reasons.length).toBeGreaterThan(0)
    expect(r.reasons.join(' ')).toMatch(/market|Category|Verification|stage/i)
  })
})

describe('rankPartners', () => {
  const partners = [
    { id: 'p1', categories: ['beauty'], markets: ['JP'], stage: 'growth', trust: 0.4 },
    { id: 'p2', categories: ['beauty'], markets: ['JP'], stage: 'growth', trust: 0.9 },
    { id: 'p3', categories: ['auto'], markets: ['BR'], stage: 'enterprise', trust: 0 }
  ]

  it('equal fit ties break toward higher trust', () => {
    const ranked = rankPartners(need, partners)
    expect(ranked[0].partner.id).toBe('p2')
  })

  it('filters weak partners unless includeWeak', () => {
    expect(rankPartners(need, partners).some(r => r.partner.id === 'p3')).toBe(false)
    expect(rankPartners(need, partners, { includeWeak: true }).some(r => r.partner.id === 'p3')).toBe(true)
  })

  it('respects topN', () => {
    expect(rankPartners(need, partners, { topN: 1 })).toHaveLength(1)
  })
})
