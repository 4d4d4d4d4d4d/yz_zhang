import { describe, it, expect } from 'vitest'
import { conceptSignals, rankCandidates, GOAL_METRIC } from '../src/logic/recommend.js'

const CONCEPT = {
  id: 'c1', name: 'Before / after reveal', format: '9:16 reel', market: 'JP',
  ctr: 4.8, cvr: 3.2, roas: 4.1, minBudget: 20000,
  audiences: ['gen-z', 'urban'], voice: 'warm',
  scores: { relevance: 94, creativity: 86, fit: 92, risk: 88 }
}
const RICH = { audience: ['gen-z', 'urban'], voice: 'warm', goal: 'roas', budget: 40000 }

describe('conceptSignals — the brief must drive the signals', () => {
  it('selects the performance metric from the goal', () => {
    const roas = conceptSignals(CONCEPT, { ...RICH, goal: 'roas' }).performance
    const reach = conceptSignals(CONCEPT, { ...RICH, goal: 'reach' }).performance
    const cpa = conceptSignals(CONCEPT, { ...RICH, goal: 'cpa' }).performance
    expect(roas).toBeCloseTo(4.1 / 7, 6)
    expect(reach).toBeCloseTo(4.8 / 6, 6)
    expect(cpa).toBeCloseTo(3.2 / 5, 6)
    expect(new Set([roas, reach, cpa]).size).toBe(3) // the goal genuinely matters
  })

  it('falls back to ROAS for an unknown goal', () => {
    expect(conceptSignals(CONCEPT, { ...RICH, goal: 'nonsense' }).performance)
      .toBeCloseTo(conceptSignals(CONCEPT, { ...RICH, goal: 'roas' }).performance, 6)
  })

  it('scores affinity as the share of requested audiences the concept targets', () => {
    expect(conceptSignals(CONCEPT, { ...RICH, audience: ['gen-z', 'urban'] }).affinity).toBe(1)
    expect(conceptSignals(CONCEPT, { ...RICH, audience: ['gen-z', 'parents'] }).affinity).toBe(0.5)
    expect(conceptSignals(CONCEPT, { ...RICH, audience: ['parents'] }).affinity).toBe(0)
  })

  it('is neutral (not zero) when no audience is selected', () => {
    expect(conceptSignals(CONCEPT, { ...RICH, audience: [] }).affinity).toBe(0.5)
  })

  it('rewards an exact brand-voice match', () => {
    expect(conceptSignals(CONCEPT, { ...RICH, voice: 'warm' }).brandFit).toBe(1)
    expect(conceptSignals(CONCEPT, { ...RICH, voice: 'bold' }).brandFit).toBe(0.45)
  })

  it('discounts performance a budget cannot fund', () => {
    const funded = conceptSignals(CONCEPT, { ...RICH, budget: 40000 }).performance
    const half = conceptSignals(CONCEPT, { ...RICH, budget: 10000 }).performance
    expect(half).toBeCloseTo(funded * 0.5, 6)
    expect(conceptSignals(CONCEPT, { ...RICH, budget: 0 }).performance).toBe(0)
  })

  it('does not penalise a concept with no budget floor', () => {
    const free = { ...CONCEPT, minBudget: 0 }
    expect(conceptSignals(free, { ...RICH, budget: 1 }).performance)
      .toBeCloseTo(conceptSignals(free, { ...RICH, budget: 999999 }).performance, 6)
  })

  it('keeps every signal within [0,1]', () => {
    const s = conceptSignals({ ...CONCEPT, roas: 999, scores: { creativity: 500, fit: -20 } }, RICH)
    for (const v of Object.values(s)) {
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThanOrEqual(1)
    }
  })

  it('guards empty input', () => {
    const s = conceptSignals()
    expect(Object.keys(s).sort()).toEqual(['affinity', 'brandFit', 'freshness', 'localization', 'performance'])
    expect(s.performance).toBe(0)
  })

  it('exposes the goal→metric map', () => {
    expect(Object.keys(GOAL_METRIC).sort()).toEqual(['cpa', 'reach', 'roas'])
  })
})

describe('end-to-end: the brief changes the ranking', () => {
  const concepts = [
    { id: 'reel-a', format: '9:16 reel', ctr: 5.2, cvr: 2.0, roas: 2.4, audiences: ['gen-z'], voice: 'playful', scores: { creativity: 90, fit: 88 } },
    { id: 'demo-b', format: '16:9 demo', ctr: 2.4, cvr: 4.6, roas: 6.2, audiences: ['professionals'], voice: 'clinical', scores: { creativity: 70, fit: 92 } }
  ]
  const rank = ctx => rankCandidates(
    concepts.map(c => ({ ...c, signals: conceptSignals(c, ctx) })),
    { diversityPenalty: 0 }
  ).map(r => r.id)

  it('ranks the high-ROAS demo first when optimising ROAS', () => {
    expect(rank({ goal: 'roas', audience: ['professionals'], voice: 'clinical', budget: 1e6 })[0]).toBe('demo-b')
  })

  it('ranks the high-CTR reel first when optimising reach for Gen Z', () => {
    expect(rank({ goal: 'reach', audience: ['gen-z'], voice: 'playful', budget: 1e6 })[0]).toBe('reel-a')
  })

  it('produces explanations ordered by contribution', () => {
    const ranked = rankCandidates(
      concepts.map(c => ({ ...c, signals: conceptSignals(c, { goal: 'roas', audience: ['gen-z'], voice: 'playful', budget: 1e6 }) })),
      {}
    )
    const contributions = ranked[0].explanation.map(e => e.contribution)
    expect(contributions).toEqual([...contributions].sort((a, b) => b - a))
    expect(ranked[0].explanation.length).toBe(5)
  })
})
