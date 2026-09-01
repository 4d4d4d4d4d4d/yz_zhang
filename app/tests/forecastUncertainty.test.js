import { describe, it, expect } from 'vitest'
import { portfolioSd, forecastBand, projectWithUncertainty, Z_SCORES } from '../src/logic/forecast.js'

describe('portfolioSd', () => {
  it('is cv × revenue for a single channel (correlation is irrelevant)', () => {
    expect(portfolioSd([1000], { cv: 0.2 })).toBeCloseTo(200, 6)
    expect(portfolioSd([1000], { cv: 0.2, correlation: 1 })).toBeCloseTo(200, 6)
  })

  it('diversifies independent channels — spread grows slower than revenue', () => {
    const one = portfolioSd([1000], { cv: 0.2 })
    const four = portfolioSd([1000, 1000, 1000, 1000], { cv: 0.2 })
    expect(four).toBeCloseTo(one * 2, 6)       // √4 = 2, not 4
    expect(four).toBeLessThan(one * 4)          // strictly better than no diversification
  })

  it('gives no diversification when channels are perfectly correlated', () => {
    const revs = [1000, 2000, 3000]
    expect(portfolioSd(revs, { cv: 0.1, correlation: 1 })).toBeCloseTo(600, 6) // 0.1 × 6000
  })

  it('sits between the independent and correlated bounds for partial correlation', () => {
    const revs = [1000, 1000, 1000]
    const indep = portfolioSd(revs, { cv: 0.1, correlation: 0 })
    const partial = portfolioSd(revs, { cv: 0.1, correlation: 0.5 })
    const full = portfolioSd(revs, { cv: 0.1, correlation: 1 })
    expect(partial).toBeGreaterThan(indep)
    expect(partial).toBeLessThan(full)
  })

  it('clamps correlation into [0,1] and guards junk input', () => {
    const revs = [1000, 1000]
    expect(portfolioSd(revs, { cv: 0.1, correlation: 9 })).toBeCloseTo(portfolioSd(revs, { cv: 0.1, correlation: 1 }), 6)
    expect(portfolioSd(revs, { cv: 0.1, correlation: -3 })).toBeCloseTo(portfolioSd(revs, { cv: 0.1, correlation: 0 }), 6)
    expect(portfolioSd(null)).toBe(0)
    expect(portfolioSd([0, 0], { cv: 0.5 })).toBe(0)
  })
})

describe('forecastBand', () => {
  it('centres on the mean and widens with the confidence level', () => {
    const p80 = forecastBand(1000, 100, 'p80')
    const p95 = forecastBand(1000, 100, 'p95')
    expect(p80.mid).toBe(1000)
    expect(p95.hi - p95.lo).toBeGreaterThan(p80.hi - p80.lo)
    expect(p95.z).toBe(Z_SCORES.p95)
  })

  it('never returns a negative low edge', () => {
    expect(forecastBand(100, 500, 'p95').lo).toBe(0)
  })

  it('collapses to a point when there is no uncertainty', () => {
    const b = forecastBand(1000, 0)
    expect(b.lo).toBe(1000)
    expect(b.hi).toBe(1000)
  })

  it('falls back to p80 for an unknown level', () => {
    expect(forecastBand(1000, 100, 'nonsense').z).toBe(Z_SCORES.p80)
  })
})

describe('projectWithUncertainty', () => {
  const channels = [
    { id: 'a', k: 3, sat: 200, alloc: 50 },
    { id: 'b', k: 2, sat: 300, alloc: 50 }
  ]

  it('keeps the point projection and adds a band around it', () => {
    const r = projectWithUncertainty(channels, 400000, { cv: 0.2 })
    expect(r.totalRevenue).toBeGreaterThan(0)
    expect(r.rows).toHaveLength(2)
    expect(r.band.mid).toBeCloseTo(r.totalRevenue, 6)
    expect(r.band.lo).toBeLessThan(r.totalRevenue)
    expect(r.band.hi).toBeGreaterThan(r.totalRevenue)
  })

  it('reports a portfolio CV below the per-channel CV (diversification)', () => {
    const r = projectWithUncertainty(channels, 400000, { cv: 0.2 })
    expect(r.relativeCv).toBeGreaterThan(0)
    expect(r.relativeCv).toBeLessThan(0.2)
  })

  it('has zero spread and zero CV at zero budget', () => {
    const r = projectWithUncertainty(channels, 0, { cv: 0.2 })
    expect(r.sd).toBe(0)
    expect(r.relativeCv).toBe(0)
  })
})
