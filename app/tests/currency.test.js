import { describe, it, expect } from 'vitest'
import { CURRENCIES, convertPrice, formatPrice, defaultCurrencyFor } from '../src/logic/currency.js'

describe('convertPrice — psychological rounding per market', () => {
  it('Growth $499: ¥ rounds to hundreds, CN¥ to tens, € to units', () => {
    expect(convertPrice(499, 'JPY')).toBe(77300) // 77,345 → hundreds
    expect(convertPrice(499, 'CNY')).toBe(3620)  // 3,617.75 → tens
    expect(convertPrice(499, 'EUR')).toBe(459)   // 459.08 → units
    expect(convertPrice(499, 'USD')).toBe(499)
  })

  it('yearly $399 follows the same rules', () => {
    expect(convertPrice(399, 'JPY')).toBe(61800) // 61,845 → 61,800
    expect(convertPrice(399, 'CNY')).toBe(2890)  // 2,892.75 → 2,890
    expect(convertPrice(399, 'EUR')).toBe(367)
  })

  it('zero stays zero in every currency', () => {
    for (const code of Object.keys(CURRENCIES)) expect(convertPrice(0, code)).toBe(0)
  })

  it('unknown currency throws — never a silently wrong price', () => {
    expect(() => convertPrice(499, 'XYZ')).toThrow(/unknown currency/)
  })
})

describe('formatPrice — Intl output', () => {
  it('renders symbols with no fraction digits', () => {
    expect(formatPrice(499, 'JPY', 'ja')).toBe('￥77,300')
    expect(formatPrice(499, 'EUR', 'en')).toBe('€459')
    expect(formatPrice(499, 'USD', 'en')).toBe('$499')
  })

  it('CNY in a zh locale carries the yuan symbol', () => {
    const s = formatPrice(499, 'CNY', 'zh')
    expect(s).toMatch(/[¥￥]/)
    expect(s).toContain('3,620')
  })
})

describe('defaultCurrencyFor', () => {
  it('maps supported locales and falls back to USD', () => {
    expect(defaultCurrencyFor('en')).toBe('USD')
    expect(defaultCurrencyFor('es')).toBe('EUR')
    expect(defaultCurrencyFor('ja')).toBe('JPY')
    expect(defaultCurrencyFor('zh')).toBe('CNY')
    expect(defaultCurrencyFor('fr')).toBe('USD')
  })
})
