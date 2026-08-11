import { describe, it, expect } from 'vitest'
import { discountZopa, surplusSplit, zopa, suggestAnchor, discountAnchor } from '../src/logic/negotiation.js'

// The shipped playbook numbers, given coherent semantics:
// seller tolerates at most 52% off; buyer requires at least 44% off.
const BUYER_MIN = 44
const SELLER_MAX = 52

describe('discountZopa', () => {
  it('spans buyer minimum → seller maximum', () => {
    const z = discountZopa(BUYER_MIN, SELLER_MAX)
    expect(z.exists).toBe(true)
    expect(z.low).toBe(44)
    expect(z.high).toBe(52)
    expect(z.width).toBe(8)
    expect(z.midpoint).toBe(48)
  })

  it('has no zone when the buyer needs more than the seller will give', () => {
    const z = discountZopa(60, 52)
    expect(z.exists).toBe(false)
    expect(z.width).toBe(0)
  })

  it('is a degenerate single point when the walk-aways meet exactly', () => {
    const z = discountZopa(50, 50)
    expect(z.exists).toBe(true)
    expect(z.width).toBe(0)
    expect(z.midpoint).toBe(50)
  })

  it('is the same rule as zopa() — one implementation', () => {
    expect(discountZopa(BUYER_MIN, SELLER_MAX)).toEqual(zopa({ max: SELLER_MAX }, { min: BUYER_MIN }))
  })
})

describe('REGRESSION — the ZOPA band must be renderable', () => {
  it('produces a positive-width zone for the shipped playbook numbers', () => {
    // The old inline math mixed targets with reservations and multiplied by
    // 1.1, yielding start(52) > end(48.4) so the band never drew.
    const z = discountZopa(BUYER_MIN, SELLER_MAX)
    expect(z.exists).toBe(true)
    expect(z.high).toBeGreaterThan(z.low)
    expect(z.width).toBeGreaterThan(0)
  })
})

describe('surplusSplit', () => {
  const z = discountZopa(BUYER_MIN, SELLER_MAX)

  it('splits the zone evenly at the midpoint', () => {
    const s = surplusSplit(z, 48)
    expect(s.buyerShare).toBeCloseTo(0.5, 6)
    expect(s.sellerShare).toBeCloseTo(0.5, 6)
  })

  it('gives the seller everything at the buyer-minimum edge', () => {
    const s = surplusSplit(z, 44)
    expect(s.buyerShare).toBeCloseTo(0, 6)
    expect(s.sellerShare).toBeCloseTo(1, 6)
  })

  it('gives the buyer everything at the seller-maximum edge', () => {
    const s = surplusSplit(z, 52)
    expect(s.buyerShare).toBeCloseTo(1, 6)
    expect(s.sellerShare).toBeCloseTo(0, 6)
  })

  it('shares always sum to 1', () => {
    for (const point of [44, 46, 48, 50, 52]) {
      const s = surplusSplit(z, point)
      expect(s.buyerShare + s.sellerShare).toBeCloseTo(1, 6)
    }
  })

  it('clamps a settlement outside the zone', () => {
    expect(surplusSplit(z, 99).settlement).toBe(52)
    expect(surplusSplit(z, 0).settlement).toBe(44)
  })

  it('is null without a usable zone', () => {
    expect(surplusSplit(discountZopa(60, 52), 50)).toBeNull()
    expect(surplusSplit(discountZopa(50, 50), 50)).toBeNull() // zero width
    expect(surplusSplit(null, 50)).toBeNull()
  })
})

describe('discountAnchor — axis-aware anchoring', () => {
  const z = discountZopa(BUYER_MIN, SELLER_MAX)

  it('anchors both sides inside the zone', () => {
    for (const side of ['seller', 'buyer']) {
      const a = discountAnchor(z, side)
      expect(a).toBeGreaterThanOrEqual(z.low)
      expect(a).toBeLessThanOrEqual(z.high)
    }
  })

  it('anchors the seller toward the SMALL discount and the buyer toward the large one', () => {
    expect(discountAnchor(z, 'seller')).toBeLessThan(z.midpoint)
    expect(discountAnchor(z, 'buyer')).toBeGreaterThan(z.midpoint)
  })

  it('inverts the price-framed suggestAnchor, which favours the seller at the high end', () => {
    expect(suggestAnchor(z, 'seller')).toBeGreaterThan(z.midpoint) // price framing
    expect(discountAnchor(z, 'seller')).toBeLessThan(z.midpoint)   // discount framing
  })

  it('is null without a zone', () => {
    expect(discountAnchor(discountZopa(60, 52), 'seller')).toBeNull()
  })
})
