import { describe, it, expect } from 'vitest'
import { channelRollup, allocateBudget, pacingStatus, percentShares } from '../src/logic/marketing.js'

describe('percentShares', () => {
  it('always totals exactly 100', () => {
    // Independent rounding of these gives 36+38+22+5 = 101.
    const shares = percentShares({ Meta: 35513, TikTok: 37826, Google: 21661, YouTube: 5000 })
    expect(Object.values(shares).reduce((s, v) => s + v, 0)).toBe(100)
  })

  it('stays within one point of the exact share', () => {
    const amounts = { Meta: 35513, TikTok: 37826, Google: 21661, YouTube: 5000 }
    const total = Object.values(amounts).reduce((s, v) => s + v, 0)
    const shares = percentShares(amounts)
    for (const [k, v] of Object.entries(amounts)) {
      expect(Math.abs(shares[k] - (v / total) * 100)).toBeLessThan(1)
    }
  })

  it('handles an exact split and a single bucket', () => {
    expect(percentShares({ a: 25, b: 25, c: 25, d: 25 })).toEqual({ a: 25, b: 25, c: 25, d: 25 })
    expect(percentShares({ only: 999 })).toEqual({ only: 100 })
  })

  it('gives every bucket 0 when there is nothing to share', () => {
    expect(percentShares({ a: 0, b: 0 })).toEqual({ a: 0, b: 0 })
    expect(percentShares(null)).toEqual({})
  })

  it('is deterministic when remainders tie', () => {
    const a = percentShares({ x: 1, y: 1, z: 1 })
    const b = percentShares({ x: 1, y: 1, z: 1 })
    expect(a).toEqual(b)
    expect(Object.values(a).reduce((s, v) => s + v, 0)).toBe(100)
  })
})

describe('channelRollup', () => {
  it('groups campaigns by channel and sums spend', () => {
    const rows = channelRollup([
      { channel: 'TikTok', spend: 100, roas: 4 },
      { channel: 'TikTok', spend: 300, roas: 2 },
      { channel: 'Meta', spend: 50, roas: 3 }
    ])
    const tiktok = rows.find(r => r.id === 'TikTok')
    expect(tiktok.spend).toBe(400)
    expect(tiktok.campaigns).toBe(2)
    expect(rows).toHaveLength(2)
  })

  it('weights ROAS by spend rather than averaging ratios', () => {
    // A tiny 10x campaign next to heavy 2x spend. Mean of ratios = 6.0,
    // which would badly misrepresent the channel; the truth is ~2.08.
    const [tiktok] = channelRollup([
      { channel: 'TikTok', spend: 10, roas: 10 },
      { channel: 'TikTok', spend: 990, roas: 2 }
    ])
    expect(tiktok.roas).toBeCloseTo((10 * 10 + 990 * 2) / 1000, 6)
    expect(tiktok.roas).toBeLessThan(2.2)
    expect(tiktok.roas).not.toBeCloseTo(6, 1) // the mean-of-ratios trap
  })

  it('reports 0 ROAS for a zero-spend channel without NaN', () => {
    const [draft] = channelRollup([{ channel: 'YouTube', spend: 0, roas: 0 }])
    expect(draft.roas).toBe(0)
    expect(Number.isNaN(draft.roas)).toBe(false)
  })

  it('ranks channels by spend descending', () => {
    const rows = channelRollup([
      { channel: 'Small', spend: 10, roas: 1 },
      { channel: 'Big', spend: 999, roas: 1 }
    ])
    expect(rows.map(r => r.id)).toEqual(['Big', 'Small'])
  })

  it('ignores campaigns without a channel and guards bad input', () => {
    expect(channelRollup([{ spend: 100, roas: 2 }])).toEqual([])
    expect(channelRollup(null)).toEqual([])
    expect(channelRollup()).toEqual([])
  })
})

describe('rollup feeds the allocator', () => {
  const campaigns = [
    { channel: 'TikTok', spend: 38200, roas: 4.0 },
    { channel: 'Meta', spend: 32600, roas: 3.4 },
    { channel: 'Google', spend: 6400, roas: 1.9 }
  ]

  it('allocates the full budget across rolled-up channels', () => {
    const channels = channelRollup(campaigns).map(c => ({ id: c.id, roas: c.roas, min: 1000 }))
    const { allocations } = allocateBudget(90000, channels)
    const total = Object.values(allocations).reduce((s, v) => s + v, 0)
    expect(total).toBeCloseTo(90000, 2)
  })

  it('gives the highest-ROAS channel the largest share', () => {
    const channels = channelRollup(campaigns).map(c => ({ id: c.id, roas: c.roas, min: 1000 }))
    const { allocations } = allocateBudget(90000, channels)
    const top = Object.entries(allocations).sort((a, b) => b[1] - a[1])[0][0]
    expect(top).toBe('TikTok')
  })

  it('respects channel caps', () => {
    const channels = [
      { id: 'A', roas: 9, min: 0, max: 1000 },
      { id: 'B', roas: 1, min: 0 }
    ]
    const { allocations } = allocateBudget(10000, channels)
    expect(allocations.A).toBeLessThanOrEqual(1000)
    expect(allocations.A + allocations.B).toBeCloseTo(10000, 2)
  })
})

describe('pacingStatus drives the pacing panel', () => {
  it('flags overspend beyond the tolerance band', () => {
    const p = pacingStatus(100000, 65000, 15, 30) // target 50k, delta 15k > 10k band
    expect(p.status).toBe('over')
    expect(p.delta).toBeCloseTo(15000, 6)
    expect(p.projectedTotal).toBeCloseTo(130000, 6)
  })

  it('treats the band edge as still on-track (inclusive tolerance)', () => {
    // delta exactly equals the ±10% band — not yet a breach.
    const p = pacingStatus(100000, 60000, 15, 30)
    expect(p.delta).toBeCloseTo(10000, 6)
    expect(p.status).toBe('on-track')
  })

  it('flags underspend and on-track inside the band', () => {
    expect(pacingStatus(100000, 30000, 15, 30).status).toBe('under')
    expect(pacingStatus(100000, 52000, 15, 30).status).toBe('on-track')
  })
})
