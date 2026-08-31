import { describe, it, expect } from 'vitest'
import { landedCost, priceForMargin, charmPrice, applyCharm, CHARM } from '../src/logic/landedCost.js'

describe('landedCost', () => {
  it('assesses duty on CIF, not on the ex-works price', () => {
    const withFreight = landedCost({ fob: 100, freight: 20, insurance: 5, dutyPct: 10 })
    expect(withFreight.cif).toBe(125)
    expect(withFreight.duty).toBe(12.5) // not 10 — the classic understatement
    expect(withFreight.total).toBe(137.5)
  })

  it('brokerage rides on CIF too, and fixed costs do not', () => {
    const c = landedCost({ fob: 200, freight: 50, dutyPct: 5, brokeragePct: 2, otherFixed: 30 })
    expect(c.cif).toBe(250)
    expect(c.duty).toBe(12.5)
    expect(c.brokerage).toBe(5)
    expect(c.total).toBe(297.5)
  })

  it('reports the share that is pure border friction', () => {
    const c = landedCost({ fob: 100, freight: 0, dutyPct: 25 })
    expect(c.borderPct).toBe(20) // 25 of 125
    expect(landedCost({ fob: 100, dutyPct: 0 }).borderPct).toBe(0)
  })

  it('is zero-safe and rejects negatives rather than crediting them', () => {
    expect(landedCost().total).toBe(0)
    expect(landedCost({}).borderPct).toBe(0)
    expect(landedCost({ fob: -50, freight: -10, dutyPct: -5 }).total).toBe(0)
  })
})

describe('priceForMargin', () => {
  // The naive formula is cost / (1 - margin). It is wrong whenever a payment
  // fee exists, because the fee scales with the price being solved for.
  it('hits the target margin exactly, fee and VAT included', () => {
    const q = priceForMargin({ landed: 100, targetMarginPct: 60, vatPct: 20, paymentFeePct: 2.9 })
    expect(q.marginPct).toBeCloseTo(60, 1)

    // Reconstruct the money flow from the reported numbers.
    const collected = q.gross
    const remitted = q.vat
    const fee = q.paymentFee
    expect(collected - remitted - fee).toBeCloseTo(q.net, 1)
    expect((q.net - 100) / q.net * 100).toBeCloseTo(60, 1)
  })

  it('beats the naive formula, which undershoots whenever a fee exists', () => {
    const naive = 100 / (1 - 0.6) // 250 ex-VAT
    const q = priceForMargin({ landed: 100, targetMarginPct: 60, vatPct: 20, paymentFeePct: 2.9 })
    expect(q.exVat).toBeGreaterThan(naive)

    // Ship the naive price and the margin actually lands under target.
    const naiveGross = naive * 1.2
    const naiveNet = naiveGross - naive * 0.2 - naiveGross * 0.029
    expect((naiveNet - 100) / naiveNet * 100).toBeLessThan(60)
  })

  it('with no VAT and no fee it collapses to the textbook formula', () => {
    const q = priceForMargin({ landed: 100, targetMarginPct: 50 })
    expect(q.exVat).toBe(200)
    expect(q.gross).toBe(200)
    expect(q.vat).toBe(0)
  })

  it('VAT never enters the margin numerator', () => {
    const a = priceForMargin({ landed: 100, targetMarginPct: 50, vatPct: 0 })
    const b = priceForMargin({ landed: 100, targetMarginPct: 50, vatPct: 25 })
    expect(a.net).toBe(b.net) // same money kept; the buyer just pays more
    expect(b.gross).toBeGreaterThan(a.gross)
  })

  it('returns null for an unreachable target instead of a negative price', () => {
    expect(priceForMargin({ landed: 100, targetMarginPct: 100 })).toBeNull()
    expect(priceForMargin({ landed: 100, targetMarginPct: 140 })).toBeNull()
    expect(priceForMargin({ landed: 100, targetMarginPct: 50, vatPct: 20, paymentFeePct: 90 })).toBeNull()
    expect(priceForMargin({ landed: 0, targetMarginPct: 50 })).toBeNull()
    expect(priceForMargin()).toBeNull()
  })
})

describe('charmPrice', () => {
  it('rounds UP to the charm point — rounding down gives away margin', () => {
    expect(charmPrice(24.1, 'end99')).toBe(24.99)
    expect(charmPrice(24.99, 'end99')).toBe(24.99)
    expect(charmPrice(25.0, 'end99')).toBe(25.99)
  })

  it('honours per-market granularity', () => {
    expect(charmPrice(2870, 'end90')).toBe(2890)
    expect(charmPrice(28600, 'end900')).toBe(28900)
    expect(charmPrice(24.2, 'end95')).toBe(24.95)
    expect(charmPrice(24.2, 'whole')).toBe(25)
  })

  it('an unknown convention falls back to whole units rather than throwing', () => {
    expect(charmPrice(24.2, 'nope')).toBe(25)
  })

  it('is zero-safe', () => {
    expect(charmPrice(0)).toBe(0)
    expect(charmPrice(-5)).toBe(0)
    expect(charmPrice(undefined)).toBe(0)
  })

  it('every declared convention lands on its own ending', () => {
    for (const [key, c] of Object.entries(CHARM)) {
      const p = charmPrice(1234.56, key)
      expect((p % c.step).toFixed(c.decimals), key).toBe(c.ending.toFixed(c.decimals))
      expect(p, key).toBeGreaterThanOrEqual(1234.56)
    }
  })
})

describe('applyCharm', () => {
  it('reports what the rounding did to the margin instead of assuming it is free', () => {
    const q = priceForMargin({ landed: 100, targetMarginPct: 55, vatPct: 20, paymentFeePct: 2.9 })
    const charmed = applyCharm(q, 'end99', { vatPct: 20, paymentFeePct: 2.9 })
    expect(charmed.gross).toBeGreaterThanOrEqual(q.gross)
    // Rounding up can only help margin, and the delta is stated, not implied.
    expect(charmed.marginDelta).toBeGreaterThanOrEqual(0)
    expect(charmed.marginPct).toBeGreaterThanOrEqual(q.marginPct)
    expect(charmed.marginPct - q.marginPct).toBeCloseTo(charmed.marginDelta, 1)
  })

  it('the charmed money flow still reconciles', () => {
    const q = priceForMargin({ landed: 80, targetMarginPct: 50, vatPct: 10, paymentFeePct: 3 })
    const c = applyCharm(q, 'end90', { vatPct: 10, paymentFeePct: 3 })
    expect(c.gross - c.vat - c.paymentFee).toBeCloseTo(c.net, 1)
  })

  it('rounds in the shopper’s currency, not in USD', () => {
    const q = priceForMargin({ landed: 78, targetMarginPct: 58, vatPct: 10, paymentFeePct: 3.6 })
    // ¥ charm points are multiples of 100 ending in 90. Rounding the USD price
    // to a ¥ convention and converting afterwards lands on a charm price in
    // neither currency and moves the margin by double digits.
    const jpy = applyCharm(q, 'end90', { vatPct: 10, paymentFeePct: 3.6, fx: 152 })
    expect(jpy.localGross % 100).toBe(90)
    expect(jpy.marginDelta).toBeLessThan(1)

    const wrong = applyCharm(q, 'end90', { vatPct: 10, paymentFeePct: 3.6 }) // fx defaulted to 1
    expect(wrong.marginDelta).toBeGreaterThan(10)
  })

  it('an absent or nonsense rate falls back to 1:1 rather than dividing by zero', () => {
    const q = priceForMargin({ landed: 100, targetMarginPct: 50 })
    for (const fx of [0, -3, null, undefined, 'abc']) {
      const c = applyCharm(q, 'end99', { fx })
      expect(Number.isFinite(c.gross), String(fx)).toBe(true)
      expect(c.localGross).toBe(c.gross)
    }
  })

  it('passes null through rather than fabricating a price', () => {
    expect(applyCharm(null)).toBeNull()
  })
})
