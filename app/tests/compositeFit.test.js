import { describe, it, expect } from 'vitest'
import { compositeFit, DIRECTORY_WEIGHTS } from '../src/logic/matching.js'

const fit = (cat, mkt, trust, speed) => [
  { k: 'Category match', v: cat },
  { k: 'Market match', v: mkt },
  { k: 'Trust signals', v: trust },
  { k: 'Delivery speed', v: speed }
]

// The shipped directory.
const LUMEN = fit(96, 92, 94, 88)
const AURORA = fit(92, 95, 88, 90)
const NORTHWAVE = fit(86, 90, 92, 78)
const COBALT = fit(80, 88, 96, 86)

describe('compositeFit', () => {
  it('is the weighted average of the dimensions', () => {
    // 0.30·96 + 0.30·92 + 0.25·94 + 0.15·88 = 93.1
    expect(compositeFit(LUMEN).score).toBeCloseTo(93.1, 6)
  })

  it('contributions sum to the score and are ordered largest first', () => {
    const { score, contributions } = compositeFit(NORTHWAVE)
    expect(contributions.reduce((s, c) => s + c.contribution, 0)).toBeCloseTo(score, 6)
    const vals = contributions.map(c => c.contribution)
    expect(vals).toEqual([...vals].sort((a, b) => b - a))
  })

  it('weights sum to 1 across the directory dimensions', () => {
    expect(Object.values(DIRECTORY_WEIGHTS).reduce((s, w) => s + w, 0)).toBeCloseTo(1, 6)
  })
})

describe('REGRESSION — the composite must not contradict its own bars', () => {
  it('ranks Northwave above Cobalt, unlike the asserted scores', () => {
    // Asserted: Cobalt 90 > Northwave 88. Their own fit bars say otherwise.
    const northwave = compositeFit(NORTHWAVE).score
    const cobalt = compositeFit(COBALT).score
    expect(northwave).toBeGreaterThan(cobalt)
    expect(northwave).toBeCloseTo(87.5, 6)
    expect(cobalt).toBeCloseTo(87.3, 6)
  })

  it('preserves the top two, which were already consistent', () => {
    const scores = [
      ['Lumen', compositeFit(LUMEN).score],
      ['Aurora', compositeFit(AURORA).score],
      ['Northwave', compositeFit(NORTHWAVE).score],
      ['Cobalt', compositeFit(COBALT).score]
    ].sort((a, b) => b[1] - a[1]).map(r => r[0])
    expect(scores).toEqual(['Lumen', 'Aurora', 'Northwave', 'Cobalt'])
  })
})

describe('guards', () => {
  it('ignores unknown dimensions', () => {
    const withNoise = [...LUMEN, { k: 'Astrological alignment', v: 100 }]
    expect(compositeFit(withNoise).score).toBeCloseTo(compositeFit(LUMEN).score, 6)
  })

  it('renormalises when a dimension was not measured', () => {
    // Only category and market present → weights 0.30/0.30 renormalise to 0.5/0.5.
    const partial = [{ k: 'Category match', v: 100 }, { k: 'Market match', v: 80 }]
    expect(compositeFit(partial).score).toBeCloseTo(90, 6)
  })

  it('does not treat a missing dimension as a zero', () => {
    const partial = [{ k: 'Category match', v: 100 }, { k: 'Market match', v: 100 }]
    expect(compositeFit(partial).score).toBeCloseTo(100, 6)
  })

  it('clamps out-of-range values', () => {
    expect(compositeFit([{ k: 'Category match', v: 500 }]).score).toBe(100)
    expect(compositeFit([{ k: 'Category match', v: -50 }]).score).toBe(0)
  })

  it('returns a zero composite for empty or unusable input', () => {
    expect(compositeFit([])).toEqual({ score: 0, contributions: [] })
    expect(compositeFit(null)).toEqual({ score: 0, contributions: [] })
    expect(compositeFit([{ k: 'nope', v: 90 }])).toEqual({ score: 0, contributions: [] })
  })
})
