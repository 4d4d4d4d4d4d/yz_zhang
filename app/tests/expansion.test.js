import { describe, it, expect } from 'vitest'
import {
  expansionScore, scoreBreakdown, expectedValue, rankOpportunities,
  strongestByTag, SIGNAL_WEIGHTS, STRENGTH
} from '../src/logic/expansion.js'

const ALL_HIGH = Object.keys(SIGNAL_WEIGHTS).map(tag => ({ tag, strength: 'high' }))

describe('expansionScore', () => {
  it('is 100 only when every signal type is present at high strength', () => {
    expect(expansionScore(ALL_HIGH)).toBe(100)
  })

  it('is 0 with no signals', () => {
    expect(expansionScore([])).toBe(0)
    expect(expansionScore(null)).toBe(0)
  })

  it('scales with strength', () => {
    const high = expansionScore([{ tag: 'intent', strength: 'high' }])
    const med = expansionScore([{ tag: 'intent', strength: 'med' }])
    const low = expansionScore([{ tag: 'intent', strength: 'low' }])
    expect(high).toBeGreaterThan(med)
    expect(med).toBeGreaterThan(low)
    expect(low).toBeGreaterThan(0)
  })

  it('ranks intent above health at equal strength — weights are not uniform', () => {
    expect(expansionScore([{ tag: 'intent', strength: 'high' }]))
      .toBeGreaterThan(expansionScore([{ tag: 'health', strength: 'high' }]))
  })

  it('does not double-count a repeated signal type', () => {
    const once = expansionScore([{ tag: 'usage', strength: 'high' }])
    const twice = expansionScore([
      { tag: 'usage', strength: 'high' },
      { tag: 'usage', strength: 'high' }
    ])
    expect(twice).toBe(once)
  })

  it('keeps the strongest observation when a type repeats', () => {
    const best = strongestByTag([
      { tag: 'usage', strength: 'low' },
      { tag: 'usage', strength: 'high' }
    ])
    expect(best.get('usage')).toBe(STRENGTH.high)
  })

  it('ignores unknown tags and malformed strengths', () => {
    expect(expansionScore([{ tag: 'astrology', strength: 'high' }])).toBe(0)
    expect(expansionScore([{ tag: 'usage', strength: 'enormous' }])).toBe(0)
    expect(expansionScore([{}])).toBe(0)
  })

  it('missing signal types genuinely lower the score', () => {
    const partial = expansionScore([{ tag: 'intent', strength: 'high' }, { tag: 'usage', strength: 'high' }])
    expect(partial).toBeGreaterThan(0)
    expect(partial).toBeLessThan(100)
  })
})

describe('scoreBreakdown', () => {
  it('explains the score, largest contribution first', () => {
    const rows = scoreBreakdown(ALL_HIGH)
    const contributions = rows.map(r => r.contribution)
    expect(contributions).toEqual([...contributions].sort((a, b) => b - a))
    expect(rows[0].tag).toBe('intent') // highest weight
  })

  it('contributions sum to the score', () => {
    const signals = [
      { tag: 'intent', strength: 'high' },
      { tag: 'usage', strength: 'med' },
      { tag: 'team', strength: 'low' }
    ]
    const sum = scoreBreakdown(signals).reduce((s, r) => s + r.contribution, 0)
    expect(Math.round(sum)).toBe(expansionScore(signals))
  })

  it('is empty with no usable signals', () => {
    expect(scoreBreakdown([{ tag: 'nope', strength: 'high' }])).toEqual([])
  })
})

describe('expectedValue', () => {
  it('discounts upside by propensity', () => {
    expect(expectedValue(50, 4000)).toBe(2000)
    expect(expectedValue(100, 4000)).toBe(4000)
    expect(expectedValue(0, 4000)).toBe(0)
  })
  it('guards junk', () => {
    expect(expectedValue('x', 4000)).toBe(0)
    expect(expectedValue(50, undefined)).toBe(0)
  })
})

describe('rankOpportunities', () => {
  it('orders by expected value, not raw upside', () => {
    const ranked = rankOpportunities([
      // Big upside but weak evidence: 0.10 weight at med → low score.
      { id: 'longshot', upside: 10000, signals: [{ tag: 'feature', strength: 'med' }] },
      // Smaller upside, overwhelming evidence.
      { id: 'sureThing', upside: 4000, signals: ALL_HIGH }
    ])
    expect(ranked[0].id).toBe('sureThing')
    expect(ranked[0].expectedValue).toBeGreaterThan(ranked[1].expectedValue)
    // …even though the long shot has the larger headline number.
    expect(ranked[1].upside).toBeGreaterThan(ranked[0].upside)
  })

  it('derives the score rather than trusting an asserted one', () => {
    const [only] = rankOpportunities([{ id: 'a', score: 99, upside: 100, signals: [] }])
    expect(only.score).toBe(0) // the supplied 99 is overwritten by the evidence
  })

  it('is deterministic on ties', () => {
    const accounts = [
      { id: 'b', upside: 100, signals: ALL_HIGH },
      { id: 'a', upside: 100, signals: ALL_HIGH }
    ]
    expect(rankOpportunities(accounts).map(a => a.id)).toEqual(['a', 'b'])
  })

  it('guards bad input', () => {
    expect(rankOpportunities(null)).toEqual([])
    expect(rankOpportunities([])).toEqual([])
  })
})
