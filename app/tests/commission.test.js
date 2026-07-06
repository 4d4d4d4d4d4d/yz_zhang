import { describe, it, expect } from 'vitest'
import { parseCap, tierCommission, capCommission, blendedRate, earnerCommission, commissionRun } from '../src/logic/commission.js'

const TIERS = [
  { name: 'Platinum', rate: 8,  cap: '∞',     partners: 8,  gmv: 1840000 },
  { name: 'Gold',     rate: 12, cap: '$500k', partners: 22, gmv: 1240000 },
  { name: 'Silver',   rate: 16, cap: '$200k', partners: 48, gmv: 680000 },
  { name: 'Standard', rate: 20, cap: '$50k',  partners: 142, gmv: 384000 }
]
const EARNERS = [
  { name: 'Lumen Studios',      tier: 'Platinum', gmv: 384000 },
  { name: 'Northwave Partners', tier: 'Gold',     gmv: 412000 },
  { name: 'Helio Network',      tier: 'Standard', gmv:  28000 }
]

describe('parseCap', () => {
  it('parses ∞, k, m, numbers and garbage', () => {
    expect(parseCap('∞')).toBe(Infinity)
    expect(parseCap(null)).toBe(Infinity)
    expect(parseCap('$500k')).toBe(500000)
    expect(parseCap('$1.2m')).toBe(1200000)
    expect(parseCap('$50k')).toBe(50000)
    expect(parseCap(250000)).toBe(250000)
    expect(parseCap('nonsense')).toBe(Infinity) // fail-open to no cap
  })
})

describe('tierCommission (aggregate, uncapped)', () => {
  it('is gmv × rate — never capped, since aggregate GMV sums many partners', () => {
    expect(tierCommission(1240000, 12)).toBe(148800) // Gold aggregate, cap NOT applied
    expect(tierCommission(384000, 8)).toBe(30720)
  })

  it('is zero-safe on bad input', () => {
    expect(tierCommission(-5, 10)).toBe(0)
    expect(tierCommission(1000, 0)).toBe(0)
  })
})

describe('capCommission (per-partner, capped)', () => {
  it('under cap = gmv × rate', () => {
    expect(capCommission(384000, 8, '∞')).toBe(30720)
    expect(capCommission(412000, 12, '$500k')).toBe(49440)
  })

  it('over cap = cap × rate; exactly at cap is unchanged', () => {
    expect(capCommission(600000, 12, '$500k')).toBe(60000) // 500k × 12%
    expect(capCommission(500000, 12, '$500k')).toBe(60000)
    expect(capCommission(80000, 20, '$50k')).toBe(10000)   // capped at 50k × 20%
  })
})

describe('blendedRate', () => {
  it('matches the fixture blended rate (uncapped aggregates)', () => {
    // (1840000*.08 + 1240000*.12 + 680000*.16 + 384000*.20) / 4144000
    const comm = 147200 + 148800 + 108800 + 76800
    expect(blendedRate(TIERS)).toBe(Math.round(comm / 4144000 * 10000) / 100)
  })

  it('is zero-safe on empty tiers', () => {
    expect(blendedRate([])).toBe(0)
  })
})

describe('earnerCommission', () => {
  it('fixture earners equal gmv × rate (all under cap, not flagged)', () => {
    const l = earnerCommission(EARNERS[0], TIERS)
    expect(l.commission).toBe(30720)
    expect(l.capped).toBe(false)
    expect(earnerCommission(EARNERS[1], TIERS).commission).toBe(49440)
  })

  it('an over-cap earner is capped and flagged', () => {
    const big = earnerCommission({ name: 'Whale', tier: 'Gold', gmv: 900000 }, TIERS)
    expect(big.commission).toBe(60000) // 500k cap × 12%
    expect(big.capped).toBe(true)
  })

  it('unknown tier → zero commission, flagged', () => {
    const u = earnerCommission({ name: 'X', tier: 'Bronze', gmv: 1000 }, TIERS)
    expect(u.commission).toBe(0)
    expect(u.unknownTier).toBe(true)
  })
})

describe('commissionRun', () => {
  it('rolls up totals with conservation', () => {
    const run = commissionRun(TIERS, EARNERS)
    expect(run.totalGMV).toBe(4144000)
    expect(run.totalPartners).toBe(220)
    expect(run.totalCommission).toBe(run.byTier.reduce((s, t) => s + t.commission, 0))
    expect(run.earners).toHaveLength(3)
  })
})
