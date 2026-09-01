import { describe, it, expect } from 'vitest'
import {
  posture, postureByScope, postureForMarket, weightedScore, worstOf, counts, deductionsFor,
  STATUS_CAP, MAX_DEDUCTION, MARKET_SCOPE
} from '../src/logic/posture.js'

// The live fixture, so the regression numbers in the spec are the numbers here.
const FW = [
  { name: 'GDPR', region: 'EU', status: 'pass', controls: 142, score: 96 },
  { name: 'CCPA / CPRA', region: 'US', status: 'pass', controls: 88, score: 94 },
  { name: 'APPI', region: 'JP', status: 'pass', controls: 64, score: 92 },
  { name: 'LGPD', region: 'BR', status: 'warn', controls: 71, score: 78 },
  { name: 'PDPA', region: 'SEA', status: 'pass', controls: 58, score: 89 },
  { name: 'DSA', region: 'EU', status: 'warn', controls: 47, score: 81 },
  { name: 'C2PA provenance', region: 'all', status: 'pass', controls: 12, score: 100 },
  { name: 'AI Act readiness', region: 'EU', status: 'risk', controls: 38, score: 64 }
]

describe('posture · control weighting', () => {
  it('weights a framework by the control surface it covers', () => {
    // 142 controls at 96 must outweigh 12 controls at 100.
    const w = weightedScore([FW[0], FW[6]])
    const plain = (96 + 100) / 2
    expect(w).toBeCloseTo((96 * 142 + 100 * 12) / 154, 6)
    expect(w).toBeLessThan(plain)
  })

  it('ignores frameworks with no control surface rather than counting them as zero', () => {
    expect(weightedScore([{ score: 90, controls: 10 }, { score: 10, controls: 0 }])).toBe(90)
    expect(weightedScore([])).toBeNull()
    expect(weightedScore([{ score: 90, controls: 0 }])).toBeNull()
    expect(weightedScore(undefined)).toBeNull()
  })
})

describe('posture · scope isolation (the Brazil regression)', () => {
  // Shipped behaviour folded the global C2PA framework (100) into every
  // regional filter, so Brazil — the only market flagged caution — read 89.
  it('a regional score is regional; global coverage is reported beside it', () => {
    const br = posture(FW, { scope: 'BR' })
    expect(br.frameworks.map(f => f.name)).toEqual(['LGPD'])
    expect(br.global.map(f => f.name)).toEqual(['C2PA provenance'])
    expect(br.raw).toBe(78)              // was 89 with the global framework averaged in
    expect(br.score).toBeLessThanOrEqual(78)
  })

  it('the shipped mean and the corrected score disagree by enough to matter', () => {
    const shippedMean = arr => Math.round(arr.reduce((s, f) => s + f.score, 0) / arr.length)
    const shippedBR = shippedMean(FW.filter(f => f.region === 'BR' || f.region === 'all'))
    expect(shippedBR).toBe(89)
    expect(posture(FW, { scope: 'BR' }).raw).toBe(78)
  })

  it('the estate view keeps every framework, global ones included', () => {
    const all = posture(FW, { scope: 'all' })
    expect(all.frameworks).toHaveLength(FW.length)
    expect(all.global).toEqual([])
    expect(all.controls).toBe(FW.reduce((s, f) => s + f.controls, 0))
  })
})

describe('posture · a material exception is not averaged away', () => {
  it('the worst framework caps the headline', () => {
    const eu = posture(FW, { scope: 'EU' })
    expect(eu.worst.name).toBe('AI Act readiness')
    expect(eu.cap).toBe(STATUS_CAP.risk)
    expect(eu.capped).toBe(true)
    // Raw control-weighted EU is healthy-looking; the cap refuses to say so
    // while a framework sits at `risk`.
    expect(eu.raw).toBeGreaterThan(STATUS_CAP.risk)
    expect(eu.score).toBeLessThanOrEqual(STATUS_CAP.risk)
  })

  it('a caution framework caps lower than a clean one', () => {
    const br = posture(FW, { scope: 'BR' })
    expect(br.cap).toBe(STATUS_CAP.warn)
    const jp = posture(FW, { scope: 'JP' })
    expect(jp.cap).toBe(STATUS_CAP.pass)
    expect(jp.capped).toBe(false) // 92 is already under 100
    expect(jp.score).toBe(92)
  })

  it('the cap is a ceiling, not a penalty — a clean estate is unaffected', () => {
    const clean = [{ name: 'A', region: 'X', status: 'pass', controls: 10, score: 90 }]
    expect(posture(clean, { scope: 'X' }).score).toBe(90)
  })

  it('worstOf breaks a status tie on the lower score', () => {
    const tied = [
      { name: 'hi', status: 'warn', controls: 1, score: 80 },
      { name: 'lo', status: 'warn', controls: 1, score: 60 }
    ]
    expect(worstOf(tied).name).toBe('lo')
    expect(worstOf([])).toBeNull()
    expect(worstOf(undefined)).toBeNull()
  })

  it('an unknown status neither crashes nor silently caps', () => {
    const odd = [{ name: 'X', region: 'Z', status: 'mystery', controls: 5, score: 88 }]
    const r = posture(odd, { scope: 'Z' })
    expect(r.cap).toBe(100)
    expect(r.score).toBe(88)
  })
})

describe('posture · open findings deduct', () => {
  const RISKS = [
    { key: 'lgpd-scc', sev: 'high', scope: 'BR' },
    { key: 'ai-act', sev: 'high', scope: 'EU' },
    { key: 'dsa-flagger', sev: 'med', scope: 'EU' },
    { key: 'appi-training', sev: 'low', scope: 'JP' }
  ]

  it('a posture with an open high finding is not the same as one with none', () => {
    const withRisk = posture(FW, { scope: 'BR', risks: RISKS })
    const without = posture(FW, { scope: 'BR' })
    expect(withRisk.score).toBe(without.score - 6)
    expect(withRisk.deduction.items).toHaveLength(1)
  })

  it('risks are scoped — Brazil is not charged for an EU finding', () => {
    const br = posture(FW, { scope: 'BR', risks: RISKS })
    expect(br.openRisks.map(r => r.key)).toEqual(['lgpd-scc'])
  })

  it('the estate view is charged for all of them', () => {
    const all = posture(FW, { scope: 'all', risks: RISKS })
    expect(all.openRisks).toHaveLength(4)
    expect(all.deduction.gross).toBe(6 + 6 + 3 + 1)
  })

  it('a long tail of low findings cannot drive posture to zero', () => {
    const tail = Array.from({ length: 40 }, (_, i) => ({ key: `t${i}`, sev: 'low', scope: 'JP' }))
    const d = deductionsFor(tail)
    expect(d.gross).toBe(40)
    expect(d.applied).toBe(MAX_DEDUCTION)
    expect(d.capped).toBe(true)
    expect(posture(FW, { scope: 'JP', risks: tail }).score).toBe(92 - MAX_DEDUCTION)
  })

  it('score never goes negative', () => {
    const weak = [{ name: 'W', region: 'Z', status: 'risk', controls: 5, score: 4 }]
    const many = Array.from({ length: 10 }, (_, i) => ({ key: `h${i}`, sev: 'high', scope: 'Z' }))
    expect(posture(weak, { scope: 'Z', risks: many }).score).toBe(0)
  })

  it('unknown severities are ignored rather than given phantom weight', () => {
    const d = deductionsFor([{ key: 'x', sev: 'catastrophic' }, { key: 'y', sev: 'high' }])
    expect(d.items.map(i => i.key)).toEqual(['y'])
    expect(deductionsFor(undefined).gross).toBe(0)
  })
})

describe('posture · counts and contributions', () => {
  it('counts are scoped, not estate-wide', () => {
    // The shipped legend counted every framework in the world beside a score
    // labelled with one region.
    expect(counts(posture(FW, { scope: 'EU' }).frameworks)).toEqual({ pass: 1, warn: 1, risk: 1 })
    expect(counts(posture(FW, { scope: 'JP' }).frameworks)).toEqual({ pass: 1, warn: 0, risk: 0 })
    expect(counts(undefined)).toEqual({ pass: 0, warn: 0, risk: 0 })
  })

  it('contributions are shares that sum to one, heaviest first', () => {
    const eu = posture(FW, { scope: 'EU' })
    expect(eu.contributions[0].name).toBe('GDPR')
    expect(eu.contributions.reduce((s, c) => s + c.share, 0)).toBeCloseTo(1, 6)
  })
})

describe('posture · uncovered scopes', () => {
  it('no regime in scope reports uncovered, not a perfect score', () => {
    const r = posture(FW, { scope: 'ZZ' })
    expect(r.covered).toBe(false)
    expect(r.score).toBeNull()
    expect(r.raw).toBeNull()
    expect(r.frameworks).toEqual([])
  })

  it('an empty framework list is uncovered rather than an error', () => {
    expect(posture([], { scope: 'EU' }).covered).toBe(false)
    expect(posture(undefined).covered).toBe(false)
  })

  it('frameworks with no control surface are uncovered, not a zero score', () => {
    // Listing a framework that declares no controls is not evidence of
    // anything. Scoring it 0 would read as a failing audit rather than an
    // absent one.
    const r = posture([{ name: 'Draft', region: 'X', status: 'pass', controls: 0, score: 50 }], { scope: 'X' })
    expect(r.covered).toBe(false)
    expect(r.reason).toBe('no-controls')
    expect(r.score).toBeNull()
    // The frameworks are still reported, so the operator can see what is there.
    expect(r.frameworks).toHaveLength(1)
    expect(r.contributions).toEqual([])
  })

  it('the two absence reasons are distinguishable', () => {
    expect(posture([], { scope: 'ZZ' }).reason).toBe('no-regime')
    expect(posture([{ region: 'ZZ', status: 'pass', controls: 0, score: 9 }], { scope: 'ZZ' }).reason).toBe('no-controls')
    expect(posture([{ region: 'ZZ', status: 'pass', controls: 4, score: 9 }], { scope: 'ZZ' }).reason).toBeNull()
  })

  it('a partial control surface still scores on the frameworks that have one', () => {
    const r = posture([
      { name: 'Real', region: 'X', status: 'pass', controls: 20, score: 80 },
      { name: 'Draft', region: 'X', status: 'pass', controls: 0, score: 10 }
    ], { scope: 'X' })
    expect(r.covered).toBe(true)
    expect(r.raw).toBe(80)
  })
})

describe('posture · per-market resolution', () => {
  it('resolves a market through its regulatory regime', () => {
    expect(postureForMarket('DE', FW).scope).toBe('EU')
    expect(postureForMarket('DE', FW).score).toBe(posture(FW, { scope: 'EU' }).score)
    expect(postureForMarket('ID', FW).scope).toBe('SEA')
  })

  it('a market with no regime in scope says so instead of scoring', () => {
    for (const code of ['AE', 'MX']) {
      const r = postureForMarket(code, FW)
      expect(r.covered, code).toBe(false)
      expect(r.score, code).toBeNull()
      expect(r.reason, code).toBe('no-regime')
    }
  })

  it('an unknown market is uncovered, not a crash', () => {
    expect(postureForMarket('QQ', FW).covered).toBe(false)
    expect(MARKET_SCOPE.QQ).toBeUndefined()
  })

  it('an uncovered market still returns the full report shape', () => {
    // The view destructures the same fields either way; a narrower object for
    // the absent case would make every consumer branch on shape.
    const covered = postureForMarket('DE', FW)
    const absent = postureForMarket('AE', FW)
    for (const key of Object.keys(covered)) {
      expect(absent, key).toHaveProperty(key)
    }
  })

  it('postureByScope reports each scope independently', () => {
    const rows = postureByScope(FW, ['EU', 'BR', 'JP'])
    expect(rows.map(r => r.scope)).toEqual(['EU', 'BR', 'JP'])
    expect(rows.every(r => r.covered)).toBe(true)
    // Each scope's frameworks are disjoint — no leakage between regions.
    const names = rows.flatMap(r => r.frameworks.map(f => f.name))
    expect(new Set(names).size).toBe(names.length)
  })
})

// Every one of these paths exists because framework and finding rows arrive
// from a register that people edit by hand. They are exercised, not assumed.
describe('posture · hostile input', () => {
  it('null rows inside a framework list are skipped, not counted', () => {
    const withHoles = [null, { name: 'A', region: 'X', status: 'warn', controls: 10, score: 70 }, undefined]
    expect(worstOf(withHoles).name).toBe('A')
    expect(counts(withHoles)).toEqual({ pass: 0, warn: 1, risk: 0 })
    const r = posture(withHoles, { scope: 'X' })
    expect(r.covered).toBe(true)
    expect(r.frameworks).toHaveLength(1)
  })

  it('worstOf survives a list whose first entries are all holes', () => {
    expect(worstOf([null, undefined])).toBeNull()
    expect(worstOf([null, { name: 'only', status: 'pass', score: 5 }]).name).toBe('only')
  })

  it('an unknown status ranks as benign rather than throwing', () => {
    const odd = [{ name: 'weird', status: 'banana', controls: 5, score: 90 },
                 { name: 'bad', status: 'risk', controls: 5, score: 90 }]
    expect(worstOf(odd).name).toBe('bad')
  })

  it('a finding without a key falls back to its title', () => {
    const d = deductionsFor([{ sev: 'high', title: 'Untitled gap' }])
    expect(d.items[0].key).toBe('Untitled gap')
  })

  it('non-array inputs are treated as empty everywhere', () => {
    expect(counts('nope')).toEqual({ pass: 0, warn: 0, risk: 0 })
    expect(worstOf('nope')).toBeNull()
    expect(deductionsFor('nope').items).toEqual([])
    expect(weightedScore('nope')).toBeNull()
    expect(posture('nope', { scope: 'EU' }).covered).toBe(false)
    expect(posture(FW, { scope: 'EU', risks: 'nope' }).openRisks).toEqual([])
    expect(postureByScope(FW, 'nope')).toEqual([])
  })

  it('null findings inside the risk list are dropped', () => {
    const r = posture(FW, { scope: 'BR', risks: [null, { key: 'x', sev: 'high', scope: 'BR' }, undefined] })
    expect(r.openRisks).toHaveLength(1)
    expect(r.deduction.gross).toBe(6)
  })

  it('a custom global scope key is honoured', () => {
    const fw = [
      { name: 'Reg', region: 'EU', status: 'pass', controls: 10, score: 90 },
      { name: 'Everywhere', region: 'WORLD', status: 'pass', controls: 5, score: 100 }
    ]
    const eu = posture(fw, { scope: 'EU', globalScope: 'WORLD' })
    expect(eu.global.map(f => f.name)).toEqual(['Everywhere'])
    expect(eu.raw).toBe(90)
    expect(posture(fw, { scope: 'WORLD', globalScope: 'WORLD' }).frameworks).toHaveLength(2)
  })
})
