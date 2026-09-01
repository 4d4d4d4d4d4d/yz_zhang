import { describe, it, expect } from 'vitest'
import {
  scoreMarket, rankMarkets, attractivenessOf, distanceOf, paybackMonths, bandFor,
  ATTRACTIVENESS, CAGE, ENTRY_BANDS, FRICTION_CEILING
} from '../src/logic/marketEntry.js'

const perfect = {
  code: 'XX', name: 'Perfect', tam: 1, growth: 1, digital: 1, payments: 1, headroom: 1,
  distance: { cultural: 0, administrative: 0, geographic: 0, economic: 0 }
}
const hostile = {
  code: 'YY', name: 'Hostile', tam: 1, growth: 1, digital: 1, payments: 1, headroom: 1,
  distance: { cultural: 1, administrative: 1, geographic: 1, economic: 1 }
}

describe('marketEntry · attractiveness and distance stay separate', () => {
  it('a market with everything scores 100 on attractiveness', () => {
    expect(attractivenessOf(perfect).score).toBe(100)
    expect(distanceOf(perfect).score).toBe(0)
  })

  it('the big-but-hard case is visible, not averaged away', () => {
    const big = scoreMarket(hostile)
    // Attractiveness is untouched by distance — that is the whole point of
    // keeping the two frames apart.
    expect(big.attractiveness).toBe(100)
    expect(big.distance).toBe(100)
    expect(big.score).toBeCloseTo(100 * (1 - FRICTION_CEILING), 6)
  })

  it('distance is friction, never fatal — a maximally distant market still scores', () => {
    expect(scoreMarket(hostile).score).toBeGreaterThan(0)
  })

  it('contributions sum to the score, so the explanation is the calculation', () => {
    const m = { tam: 0.8, growth: 0.5, digital: 0.9, payments: 0.3, headroom: 0.6, distance: {} }
    const attr = attractivenessOf(m)
    const summed = attr.parts.reduce((s, p) => s + p.value * p.weight, 0)
    const total = Object.values(ATTRACTIVENESS).reduce((s, w) => s + w, 0)
    expect(attr.score).toBeCloseTo((summed / total) * 100, 1)
  })

  it('missing or junk inputs read as zero, not NaN', () => {
    const r = scoreMarket({ code: 'ZZ', tam: null, growth: 'abc', distance: null })
    expect(Number.isFinite(r.score)).toBe(true)
    expect(r.attractiveness).toBe(0)
    expect(r.distance).toBe(0)
    expect(scoreMarket(undefined).score).toBe(0)
  })

  it('out-of-range inputs are clamped rather than trusted', () => {
    const over = scoreMarket({ ...perfect, tam: 4, growth: 9 })
    expect(over.attractiveness).toBe(100)
    const under = scoreMarket({ ...perfect, tam: -3 })
    expect(under.attractiveness).toBeLessThan(100)
  })

  it('names the biggest barrier so the panel can say what to fix', () => {
    const r = scoreMarket({ ...perfect, distance: { cultural: 0.2, administrative: 0.9, geographic: 0.1, economic: 0.2 } })
    expect(r.topBarrier.key).toBe('administrative')
    // Weight matters, not just raw severity: economic carries the heaviest CAGE
    // weight, so an equal raw score there outranks a cultural one.
    const tie = scoreMarket({ ...perfect, distance: { cultural: 0.8, administrative: 0, geographic: 0, economic: 0.8 } })
    expect(tie.topBarrier.key).toBe('economic')
    expect(CAGE.economic).toBeGreaterThan(CAGE.cultural)
  })
})

describe('marketEntry · bands', () => {
  it('boundary values belong to the higher band', () => {
    expect(bandFor(62)).toBe('enter')
    expect(bandFor(61.9)).toBe('pilot')
    expect(bandFor(48)).toBe('pilot')
    expect(bandFor(34)).toBe('watch')
    expect(bandFor(33.9)).toBe('defer')
    expect(bandFor(0)).toBe('defer')
  })

  it('bands are declared in descending order — an out-of-order table would misroute', () => {
    for (let i = 1; i < ENTRY_BANDS.length; i++) {
      expect(ENTRY_BANDS[i].min).toBeLessThan(ENTRY_BANDS[i - 1].min)
    }
  })
})

describe('marketEntry · payback', () => {
  it('gross margin lengthens payback — the headline ARPA lies', () => {
    expect(paybackMonths(1200, 100, 100)).toBe(12)
    expect(paybackMonths(1200, 100, 40)).toBe(30)
  })

  it('returns null when payback never happens, rather than Infinity', () => {
    expect(paybackMonths(5000, 0, 60)).toBeNull()
    expect(paybackMonths(5000, 100, 0)).toBeNull()
  })

  it('free acquisition pays back immediately', () => {
    expect(paybackMonths(0, 100, 50)).toBe(0)
  })
})

describe('marketEntry · ranking', () => {
  const MARKETS = [
    { code: 'A', tam: 0.9, growth: 0.8, digital: 0.9, payments: 0.9, headroom: 0.4, distance: { cultural: 0.7, administrative: 0.8, geographic: 0.6, economic: 0.5 } },
    { code: 'B', tam: 0.6, growth: 0.7, digital: 0.8, payments: 0.9, headroom: 0.7, distance: { cultural: 0.2, administrative: 0.2, geographic: 0.3, economic: 0.2 } },
    { code: 'C', tam: 0.2, growth: 0.2, digital: 0.3, payments: 0.2, headroom: 0.2, distance: { cultural: 0.9, administrative: 0.9, geographic: 0.9, economic: 0.9 } }
  ]

  it('a close, workable market can beat a bigger, harder one', () => {
    const ranked = rankMarkets(MARKETS)
    expect(ranked[0].code).toBe('B')
    expect(ranked[0].attractiveness).toBeLessThan(ranked.find(r => r.code === 'A').attractiveness)
    expect(ranked.at(-1).code).toBe('C')
  })

  it('ties break on distance, then on code — the order is never arbitrary', () => {
    const twins = [
      { code: 'Z', tam: 0.5, growth: 0.5, digital: 0.5, payments: 0.5, headroom: 0.5, distance: { cultural: 0.5, administrative: 0.5, geographic: 0.5, economic: 0.5 } },
      { code: 'A', tam: 0.5, growth: 0.5, digital: 0.5, payments: 0.5, headroom: 0.5, distance: { cultural: 0.5, administrative: 0.5, geographic: 0.5, economic: 0.5 } }
    ]
    expect(rankMarkets(twins).map(r => r.code)).toEqual(['A', 'Z'])
  })

  it('re-weighting changes the answer — the weights are inputs, not decoration', () => {
    const distanceBlind = rankMarkets(MARKETS, { ceiling: 0 })
    expect(distanceBlind[0].code).toBe('A') // without friction, biggest wins
    expect(rankMarkets(MARKETS)[0].code).toBe('B')
  })

  it('empty and junk input rank to an empty list', () => {
    expect(rankMarkets([])).toEqual([])
    expect(rankMarkets()).toEqual([])
  })
})
