import { describe, it, expect } from 'vitest'
import { priceQuote, approvalFor } from '../src/logic/cpq.js'
import { buildSchedule } from '../src/logic/revrec.js'
import { meterBill, invoice, projectedTotal } from '../src/logic/metering.js'

// ------------------------------------------------------------------ CPQ

const CATALOG = [
  { id: 'plat', list: 1000, cost: 300 },
  { id: 'seat', list: 60, cost: 8 }
]

describe('cpq · priceQuote', () => {
  it('computes line and blended math on a fixture', () => {
    const q = priceQuote([
      { sku: 'plat', qty: 10, discount: 10 }, // gross 10000, disc 1000, net 9000, cost 3000
      { sku: 'seat', qty: 100, discount: 0 }  // gross 6000, net 6000, cost 800
    ], CATALOG)
    expect(q.totals.gross).toBe(16000)
    expect(q.totals.discount).toBe(1000)
    expect(q.totals.net).toBe(15000)
    expect(q.totals.blendedDiscount).toBeCloseTo(1000 / 16000 * 100, 6)
    expect(q.totals.blendedMargin).toBeCloseTo((15000 - 3800) / 15000 * 100, 6)
  })

  it('unknown SKUs are skipped and reported; clamps qty/discount', () => {
    const q = priceQuote([
      { sku: 'ghost', qty: 5, discount: 0 },
      { sku: 'seat', qty: -3, discount: 150 }
    ], CATALOG)
    expect(q.skipped).toEqual(['ghost'])
    expect(q.lines[0].qty).toBe(0)
    expect(q.lines[0].discount).toBe(100)
    expect(q.lines[0].margin).toBe(0) // zero-net line
  })

  it('empty quote is total-zero safe', () => {
    const q = priceQuote([], CATALOG)
    expect(q.totals).toMatchObject({ net: 0, gross: 0, blendedDiscount: 0, blendedMargin: 0 })
  })
})

describe('cpq · approvalFor', () => {
  it('boundary values belong to the lower tier (5/15/25)', () => {
    expect(approvalFor(5).level).toBe('Auto-approved')
    expect(approvalFor(5.01).level).toBe('Sales Manager')
    expect(approvalFor(15).level).toBe('Sales Manager')
    expect(approvalFor(25).level).toBe('VP Sales')
    expect(approvalFor(25.01).level).toBe('CFO + CEO')
  })
})

// -------------------------------------------------------------- rev-rec

const CONTRACT = {
  id: 'C1', tcv: 840000, term: 12,
  obligations: [
    { name: 'sub', amount: 720000, kind: 'ratable', start: 0, end: 12 },
    { name: 'onboarding', amount: 60000, kind: 'point-in-time', start: 0, end: 1 },
    { name: 'services', amount: 60000, kind: 'milestone', start: 0, end: 6 }
  ]
}

describe('revrec · buildSchedule', () => {
  it('conserves each obligation within the horizon', () => {
    const s = buildSchedule(CONTRACT, 12)
    const sum = name => s.rows.reduce((acc, r) => acc + r.obligations[name], 0)
    expect(sum('sub')).toBeCloseTo(720000, 6)
    expect(sum('onboarding')).toBe(60000)
    expect(sum('services')).toBeCloseTo(60000, 6)
    expect(s.recognized).toBeCloseTo(840000, 6)
    expect(s.deferred).toBeCloseTo(0, 6)
  })

  it('places milestones as three equal tranches at even intervals', () => {
    const s = buildSchedule({ tcv: 60000, term: 6, obligations: [
      { name: 'ms', amount: 60000, kind: 'milestone', start: 0, end: 6 }
    ] }, 6)
    const months = s.rows.map(r => r.obligations.ms)
    expect(months[0]).toBeCloseTo(20000, 6) // floor(0)
    expect(months[2]).toBeCloseTo(20000, 6) // floor(2)
    expect(months[4]).toBeCloseTo(20000, 6) // floor(4)
    expect(months[1] + months[3] + months[5]).toBe(0)
  })

  it('truncated horizon leaves the remainder deferred; cumulative is monotone', () => {
    const s = buildSchedule({ tcv: 240000, term: 24, obligations: [
      { name: 'sub', amount: 240000, kind: 'ratable', start: 0, end: 24 }
    ] }, 12)
    expect(s.recognized).toBeCloseTo(120000, 6)
    expect(s.deferred).toBeCloseTo(120000, 6)
    for (let i = 1; i < s.cumulative.length; i++) {
      expect(s.cumulative[i]).toBeGreaterThanOrEqual(s.cumulative[i - 1])
    }
  })

  it('empty contract → zero schedule, no throw', () => {
    const s = buildSchedule(undefined, 3)
    expect(s.recognized).toBe(0)
    expect(s.rows).toHaveLength(3)
  })
})

// ------------------------------------------------------------- metering

describe('metering', () => {
  it('no overage at or below the included allowance', () => {
    expect(meterBill({ used: 900, included: 1000, cost: 500 }).overage).toBe(0)
    expect(meterBill({ used: 1000, included: 1000, cost: 500 }).overage).toBe(0)
  })

  it('overage is a 40% premium on the pro-rata share past the allowance', () => {
    // 25% over → 500 × 0.25 × 0.4 = 50
    expect(meterBill({ used: 1250, included: 1000, cost: 500 }).overage).toBe(50)
  })

  it('invoice total includes base + usage + overage (spec 15 R1 correction)', () => {
    const inv = invoice(1000, [
      { used: 1250, included: 1000, cost: 500 }, // overage 50
      { used: 100, included: 200, cost: 80 }
    ])
    expect(inv.usage).toBe(580)
    expect(inv.overage).toBe(50)
    expect(inv.total).toBe(1000 + 580 + 50)
  })

  it('projects month-end linearly on usage-driven parts, base flat', () => {
    const inv = invoice(1000, [{ used: 1250, included: 1000, cost: 500 }])
    // day 15 of 30 → usage parts double
    expect(projectedTotal(inv, 15, 30)).toBe(1000 + (500 + 50) * 2)
    expect(projectedTotal(inv, 0, 30)).toBe(1000) // day-0 safe
  })
})
