// Spec 25 — multi-currency pricing. Pegged demo rates (deterministic,
// testable); production feeds live rates server-side. The permanent
// logic here is per-market psychological rounding + formatting.

export const CURRENCIES = {
  USD: { rate: 1, roundTo: 1 },
  EUR: { rate: 0.92, roundTo: 1 },
  JPY: { rate: 155, roundTo: 100 }, // quoted in hundreds: ¥77,300, never ¥77,345
  CNY: { rate: 7.25, roundTo: 10 }
}

const LOCALE_DEFAULTS = { en: 'USD', es: 'EUR', ja: 'JPY', zh: 'CNY' }

export function defaultCurrencyFor(locale) {
  return LOCALE_DEFAULTS[locale] ?? 'USD'
}

// A pricing page must fail loudly on an unknown currency — a silently
// wrong number is the worst failure mode this surface has.
export function convertPrice(usd, code) {
  const cur = CURRENCIES[code]
  if (!cur) throw new Error(`unknown currency "${code}"`)
  const raw = (Number(usd) || 0) * cur.rate
  return Math.round(raw / cur.roundTo) * cur.roundTo
}

export function formatPrice(usd, code, locale = 'en') {
  const amount = convertPrice(usd, code)
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: code,
    maximumFractionDigits: 0
  }).format(amount)
}
