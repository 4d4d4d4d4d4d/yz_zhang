import { describe, it, expect } from 'vitest'
import { convertAmount, crossBorderQuote } from '../src/logic/quote.js'

describe('convertAmount', () => {
  it('converts USD at the given rate, rounded to whole units', () => {
    expect(convertAmount(1000, 1)).toBe(1000)
    expect(convertAmount(1000, 155)).toBe(155000)
    expect(convertAmount(999.6, 1)).toBe(1000)
  })
  it('guards non-numeric input', () => {
    expect(convertAmount('x', 155)).toBe(0)
    expect(convertAmount(1000, undefined)).toBe(0)
  })
})

describe('crossBorderQuote', () => {
  it('is a no-op passthrough for USD', () => {
    const q = crossBorderQuote(864000, { code: 'USD', rate: 1 })
    expect(q).toEqual({ code: 'USD', rate: 1, netUsd: 864000, net: 864000, isUsd: true })
  })
  it('converts to a partner currency and flags non-USD', () => {
    const q = crossBorderQuote(864000, { code: 'JPY', rate: 155 })
    expect(q.code).toBe('JPY')
    expect(q.net).toBe(864000 * 155)
    expect(q.isUsd).toBe(false)
    expect(q.netUsd).toBe(864000)
  })
  it('defaults safely', () => {
    expect(crossBorderQuote()).toEqual({ code: 'USD', rate: 1, netUsd: 0, net: 0, isUsd: true })
  })
})
