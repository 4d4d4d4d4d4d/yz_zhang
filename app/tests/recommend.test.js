import { describe, it, expect } from 'vitest'
import { rankCandidates, scoreCandidate, DEFAULT_WEIGHTS } from '../src/logic/recommend.js'

const cand = (id, format, signals) => ({ id, name: id, market: 'JP', format, signals })

describe('scoreCandidate', () => {
  it('explanation contributions sum to the score', () => {
    const { score, explanation } = scoreCandidate(cand('a', 'reel', {
      affinity: 0.8, freshness: 0.5, performance: 0.9, brandFit: 0.4, localization: 0.7
    }))
    const sum = explanation.reduce((s, e) => s + e.contribution, 0)
    expect(sum).toBeCloseTo(score, 8)
  })

  it('bounds score to [0,100] and clamps bad signals', () => {
    const perfect = scoreCandidate(cand('a', 'reel', { affinity: 1, freshness: 1, performance: 1, brandFit: 1, localization: 1 }))
    expect(perfect.score).toBeCloseTo(100, 6)
    const junk = scoreCandidate(cand('b', 'reel', { affinity: 7, freshness: -3, performance: 'x' }))
    expect(junk.score).toBeGreaterThanOrEqual(0)
    expect(junk.score).toBeLessThanOrEqual(100)
  })
})

describe('rankCandidates', () => {
  it('returns [] on empty input', () => {
    expect(rankCandidates([])).toEqual([])
    expect(rankCandidates(undefined)).toEqual([])
  })

  it('is deterministic with id tiebreak', () => {
    const twins = [cand('b', 'reel', { affinity: 0.5 }), cand('a', 'reel', { affinity: 0.5 })]
    const r1 = rankCandidates(twins, { diversityPenalty: 0 })
    const r2 = rankCandidates([...twins].reverse(), { diversityPenalty: 0 })
    expect(r1.map(x => x.id)).toEqual(['a', 'b'])
    expect(r2.map(x => x.id)).toEqual(['a', 'b'])
  })

  it('weight override changes the order', () => {
    const cs = [
      cand('perf', 'reel', { performance: 1, localization: 0 }),
      cand('local', 'reel', { performance: 0, localization: 1 })
    ]
    const base = rankCandidates(cs, { diversityPenalty: 0 })
    expect(base[0].id).toBe('perf') // performance outweighs localization by default
    const flipped = rankCandidates(cs, {
      diversityPenalty: 0,
      weights: { ...DEFAULT_WEIGHTS, performance: 0.05, localization: 0.6 }
    })
    expect(flipped[0].id).toBe('local')
  })

  it('diversity penalty breaks up same-format runs; λ=0 reproduces score order', () => {
    const cs = [
      cand('reel1', 'reel', { performance: 1.0 }),
      cand('reel2', 'reel', { performance: 0.95 }),
      cand('reel3', 'reel', { performance: 0.9 }),
      cand('banner', 'banner', { performance: 0.85 })
    ]
    const pure = rankCandidates(cs, { diversityPenalty: 0 })
    expect(pure.map(x => x.id)).toEqual(['reel1', 'reel2', 'reel3', 'banner'])
    const diverse = rankCandidates(cs, { diversityPenalty: 0.5 })
    expect(diverse.map(x => x.id).indexOf('banner')).toBeLessThan(3)
  })
})
