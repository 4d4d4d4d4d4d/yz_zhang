// Spec 33 — locale-aware figure formatting. Pure Intl wrappers so console
// numbers group and abbreviate correctly per locale (a JP operator should
// never see US-style grouping). Deterministic given (value, locale); the
// view binds the current locale via useFormat. Non-finite input renders an
// em dash rather than "NaN"/"$NaN" leaking onto the page.

const DASH = '—'

function finite(n) {
  // Reject nullish/empty before Number() coerces them to 0.
  if (n === null || n === undefined || n === '') return null
  const v = Number(n)
  return Number.isFinite(v) ? v : null
}

// Grouped number: 1234567 → "1,234,567" (en) / "1.234.567" (es).
export function num(n, locale = 'en', { digits = 0 } = {}) {
  const v = finite(n)
  if (v === null) return DASH
  return new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(v)
}

// Abbreviated: 1200 → "1.2K", 3_400_000 → "3.4M".
export function compact(n, locale = 'en') {
  const v = finite(n)
  if (v === null) return DASH
  return new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }).format(v)
}

// Currency. Base currency is USD (the product bills in USD); a caller may
// override. `compact` abbreviates ($384K); `digits` controls precision.
export function money(n, { locale = 'en', currency = 'USD', digits = 0, compact: abbr = false } = {}) {
  const v = finite(n)
  if (v === null) return DASH
  return new Intl.NumberFormat(locale, {
    style: 'currency', currency,
    notation: abbr ? 'compact' : 'standard',
    maximumFractionDigits: abbr ? 1 : digits,
    minimumFractionDigits: 0
  }).format(v)
}

// Percent from a FRACTION: 0.1234 → "12.3%".
export function pct(fraction, { locale = 'en', digits = 1 } = {}) {
  const v = finite(fraction)
  if (v === null) return DASH
  return new Intl.NumberFormat(locale, {
    style: 'percent', maximumFractionDigits: digits, minimumFractionDigits: digits
  }).format(v)
}
