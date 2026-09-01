import { describe, it, expect } from 'vitest'
import { num, compact, money, pct } from '../src/logic/format.js'

describe('num — grouped numbers', () => {
  it('groups thousands (en)', () => {
    expect(num(1234567)).toBe('1,234,567')
  })
  it('groups differently per locale', () => {
    // es-ES groups with dots — must not equal the en grouping
    expect(num(1234567, 'es')).not.toBe(num(1234567, 'en'))
  })
  it('rounds to the requested digits', () => {
    expect(num(1234.56, 'en', { digits: 1 })).toBe('1,234.6')
  })
})

describe('compact — abbreviated', () => {
  it('abbreviates thousands and millions', () => {
    expect(compact(1200)).toMatch(/1\.2K/)
    expect(compact(3_400_000)).toMatch(/3\.4M/)
  })
})

describe('money — currency', () => {
  it('formats USD with a $ and grouping', () => {
    expect(money(384000)).toBe('$384,000')
  })
  it('abbreviates when compact', () => {
    expect(money(384000, { compact: true })).toMatch(/\$384K/)
  })
  it('honours a currency override', () => {
    const jpy = money(1000, { currency: 'JPY', locale: 'ja' })
    expect(jpy).toMatch(/1,000/)
    expect(jpy).not.toMatch(/\$/)
  })
})

describe('pct — percent from a fraction', () => {
  it('renders a fraction as a percentage', () => {
    expect(pct(0.1234)).toBe('12.3%')
  })
  it('honours digits', () => {
    expect(pct(0.5, { digits: 0 })).toBe('50%')
  })
})

describe('non-finite guard', () => {
  it('renders an em dash instead of NaN/$NaN', () => {
    expect(num(NaN)).toBe('—')
    expect(compact(Infinity)).toBe('—')
    expect(money(undefined)).toBe('—')
    expect(money('abc', { compact: true })).toBe('—')
    expect(pct(null)).toBe('—')
  })
})
