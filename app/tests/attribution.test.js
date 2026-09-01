import { describe, it, expect } from 'vitest'
import { attribute, attributionRows, MODELS } from '../src/logic/attribution.js'

const DAY = 86400000
// One journey: TikTok (14d before) → Email (7d before) → Direct (at conversion)
const J = [{
  convertedAt: 100 * DAY,
  touches: [
    { channel: 'TikTok', at: 86 * DAY },
    { channel: 'Email', at: 93 * DAY },
    { channel: 'Direct', at: 100 * DAY }
  ]
}]

const sum = o => Object.values(o).reduce((s, v) => s + v, 0)

describe('rule-based models', () => {
  it('first-touch gives all credit to the discovery channel', () => {
    expect(attribute(J, 'first')).toEqual({ TikTok: 1, Email: 0, Direct: 0 })
  })

  it('last-touch gives all credit to the closing channel', () => {
    expect(attribute(J, 'last')).toEqual({ TikTok: 0, Email: 0, Direct: 1 })
  })

  it('linear splits evenly', () => {
    const r = attribute(J, 'linear')
    expect(r.TikTok).toBeCloseTo(1 / 3, 6)
    expect(r.Email).toBeCloseTo(1 / 3, 6)
    expect(r.Direct).toBeCloseTo(1 / 3, 6)
  })

  it('time-decay weights recent touches by the half-life', () => {
    // 14d out → 2^-2 = .25, 7d out → 2^-1 = .5, at conversion → 1 (sum 1.75)
    const r = attribute(J, 'decay', { halfLifeDays: 7 })
    expect(r.TikTok).toBeCloseTo(0.25 / 1.75, 6)
    expect(r.Email).toBeCloseTo(0.5 / 1.75, 6)
    expect(r.Direct).toBeCloseTo(1 / 1.75, 6)
    expect(r.Direct).toBeGreaterThan(r.TikTok)
  })

  it('position-based is 40 / 20-split / 40', () => {
    const four = [{ convertedAt: 0, touches: [{ channel: 'A', at: 0 }, { channel: 'B', at: 0 }, { channel: 'C', at: 0 }, { channel: 'D', at: 0 }] }]
    const r = attribute(four, 'position')
    expect(r.A).toBeCloseTo(0.4, 6)
    expect(r.D).toBeCloseTo(0.4, 6)
    expect(r.B).toBeCloseTo(0.1, 6)
    expect(r.C).toBeCloseTo(0.1, 6)
  })

  it('position-based degrades sanely for 1 and 2 touches', () => {
    const one = [{ touches: [{ channel: 'A', at: 0 }] }]
    expect(attribute(one, 'position')).toEqual({ A: 1 })
    const two = [{ touches: [{ channel: 'A', at: 0 }, { channel: 'B', at: 0 }] }]
    const r = attribute(two, 'position')
    expect(r.A).toBeCloseTo(0.5, 6)
    expect(r.B).toBeCloseTo(0.5, 6)
  })
})

describe('shapley', () => {
  it('satisfies efficiency — credit sums to 1', () => {
    expect(sum(attribute(J, 'shapley'))).toBeCloseTo(1, 6)
  })

  it('satisfies symmetry — interchangeable channels split evenly', () => {
    const j = [{ touches: [{ channel: 'A', at: 0 }, { channel: 'B', at: 1 }], count: 10 }]
    const r = attribute(j, 'shapley')
    expect(r.A).toBeCloseTo(0.5, 6)
    expect(r.B).toBeCloseTo(0.5, 6)
  })

  it('rewards a channel that converts alone over one that never does', () => {
    const j = [
      { touches: [{ channel: 'Solo', at: 0 }], count: 50 },
      { touches: [{ channel: 'Solo', at: 0 }, { channel: 'Tagalong', at: 1 }], count: 50 }
    ]
    const r = attribute(j, 'shapley')
    expect(r.Solo).toBeGreaterThan(r.Tagalong)
  })
})

describe('weights and normalization', () => {
  it('respects the path count (aggregated journeys)', () => {
    const j = [
      { touches: [{ channel: 'A', at: 0 }], count: 90 },
      { touches: [{ channel: 'B', at: 0 }], count: 10 }
    ]
    const r = attribute(j, 'last')
    expect(r.A).toBeCloseTo(0.9, 6)
    expect(r.B).toBeCloseTo(0.1, 6)
  })

  it('every model normalizes to 1', () => {
    for (const m of MODELS) {
      expect(sum(attribute(J, m)), m).toBeCloseTo(1, 6)
    }
  })
})

describe('guards', () => {
  it('returns {} for empty or invalid input', () => {
    expect(attribute([], 'linear')).toEqual({})
    expect(attribute(null, 'linear')).toEqual({})
    expect(attribute([{ touches: [] }], 'linear')).toEqual({})
    expect(attribute([{ touches: [{ at: 0 }] }], 'linear')).toEqual({})
  })

  it('falls back to linear for an unknown model', () => {
    const r = attribute(J, 'nonsense')
    expect(r.TikTok).toBeCloseTo(1 / 3, 6)
  })

  it('decay falls back to the last touch when convertedAt is missing', () => {
    const j = [{ touches: [{ channel: 'A', at: 0 }, { channel: 'B', at: 7 * DAY }] }]
    const r = attribute(j, 'decay', { halfLifeDays: 7 })
    // B is the (implicit) conversion moment → weight 1; A is 7d earlier → 0.5
    expect(r.B).toBeCloseTo(1 / 1.5, 6)
    expect(r.A).toBeCloseTo(0.5 / 1.5, 6)
  })

  it('handles a zero-span decay journey without NaN', () => {
    const j = [{ convertedAt: 0, touches: [{ channel: 'A', at: 0 }, { channel: 'B', at: 0 }] }]
    const r = attribute(j, 'decay')
    expect(r.A).toBeCloseTo(0.5, 6)
    expect(Number.isNaN(r.B)).toBe(false)
  })
})

describe('attributionRows', () => {
  it('ranks channels by credit descending with percentages', () => {
    const rows = attributionRows(J, 'last')
    expect(rows[0].channel).toBe('Direct')
    expect(rows[0].pct).toBeCloseTo(100, 6)
    expect(rows).toHaveLength(3)
  })
  it('is empty for no journeys', () => {
    expect(attributionRows([], 'linear')).toEqual([])
  })
})
