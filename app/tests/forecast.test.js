import { describe, it, expect } from 'vitest'
import { saturatingRevenue, marginalRoas, project, rebalanceAllocations, optimalAllocation } from '../src/logic/forecast.js'

const CHANNELS = [
  { id: 'tiktok', alloc: 32, k: 4.4, sat: 90 },
  { id: 'meta',   alloc: 28, k: 3.6, sat: 110 },
  { id: 'google', alloc: 22, k: 2.8, sat: 70 },
  { id: 'youtube',alloc: 12, k: 2.1, sat: 60 },
  { id: 'email',  alloc: 6,  k: 6.2, sat: 14 }
]

describe('saturation model', () => {
  const ch = { k: 4, sat: 100 }

  it('revenue is monotone increasing and bounded by k·sat', () => {
    let prev = 0
    for (const b of [0, 10, 50, 100, 300, 1000]) {
      const r = saturatingRevenue(ch, b)
      expect(r).toBeGreaterThanOrEqual(prev)
      expect(r).toBeLessThanOrEqual(ch.k * ch.sat)
      prev = r
    }
    expect(saturatingRevenue(ch, 0)).toBe(0)
  })

  it('marginal ROAS starts at k and strictly decreases', () => {
    expect(marginalRoas(ch, 0)).toBe(ch.k)
    expect(marginalRoas(ch, 50)).toBeGreaterThan(marginalRoas(ch, 100))
    expect(marginalRoas(ch, 100)).toBeGreaterThan(marginalRoas(ch, 200))
  })
})

describe('project', () => {
  it('splits budget by alloc % and reports portfolio totals', () => {
    const { rows, totalRevenue, totalRoas } = project(CHANNELS, 200000)
    expect(rows).toHaveLength(5)
    expect(rows[0].budget).toBe(200000 * 0.32)
    expect(totalRevenue).toBeCloseTo(rows.reduce((s, r) => s + r.revenue, 0), 6)
    expect(totalRoas).toBeCloseTo(totalRevenue / 200000, 10)
  })

  it('zero-alloc channel projects zero budget and zero ROAS', () => {
    const { rows } = project([{ id: 'x', alloc: 0, k: 3, sat: 50 }, { id: 'y', alloc: 100, k: 3, sat: 50 }], 100000)
    expect(rows[0].budget).toBe(0)
    expect(rows[0].roas).toBe(0)
  })
})

describe('rebalanceAllocations', () => {
  it('moving one slider keeps the sum at exactly 100', () => {
    for (const val of [0, 15, 50, 87, 100]) {
      const next = rebalanceAllocations(CHANNELS, 'tiktok', val)
      const sum = Object.values(next).reduce((s, v) => s + v, 0)
      expect(sum).toBe(100)
      expect(next.tiktok).toBe(val)
    }
  })

  it('others shrink proportionally when one grows', () => {
    const next = rebalanceAllocations(CHANNELS, 'tiktok', 52) // +20
    expect(next.meta).toBeLessThan(28)
    expect(next.google).toBeLessThan(22)
  })

  it('clamps out-of-range values and ignores unknown ids', () => {
    expect(rebalanceAllocations(CHANNELS, 'tiktok', 250).tiktok).toBe(100)
    const unchanged = rebalanceAllocations(CHANNELS, 'nope', 50)
    expect(unchanged).toEqual(Object.fromEntries(CHANNELS.map(c => [c.id, c.alloc])))
  })
})

describe('optimalAllocation', () => {
  it('returns integer percentages summing to 100', () => {
    const opt = optimalAllocation(CHANNELS, 200000)
    expect(opt).not.toBeNull()
    const vals = Object.values(opt)
    expect(vals.reduce((s, v) => s + v, 0)).toBe(100)
    for (const v of vals) expect(Number.isInteger(v)).toBe(true)
  })

  it('never projects worse revenue than the uniform split', () => {
    const opt = optimalAllocation(CHANNELS, 200000)
    const optimized = CHANNELS.map(c => ({ ...c, alloc: opt[c.id] }))
    const uniform = CHANNELS.map(c => ({ ...c, alloc: 20 }))
    expect(project(optimized, 200000).totalRevenue)
      .toBeGreaterThanOrEqual(project(uniform, 200000).totalRevenue)
  })

  it('shifts budget toward high-marginal channels vs the default hand split', () => {
    const opt = optimalAllocation(CHANNELS, 200000)
    const optimized = CHANNELS.map(c => ({ ...c, alloc: opt[c.id] }))
    expect(project(optimized, 200000).totalRevenue)
      .toBeGreaterThanOrEqual(project(CHANNELS, 200000).totalRevenue - 1e-6)
  })
})
