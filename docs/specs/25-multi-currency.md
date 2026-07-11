# Spec 25 — Multi-Currency Pricing (出海定价本地化)

Status: **Approved** · Review: R1 (2026-07-05)
Domains: `logic/currency.js` · `views/Pricing.vue`

## Problem

A go-global product showing `$499` to a buyer in Osaka adds conversion
friction at the exact moment of intent. Industry-standard global SaaS
pricing pages (Stripe, Shopify, Notion) localize the displayed currency,
defaulting from the visitor's locale with a manual override. Ours is
USD-only — and the `Free` / `Custom` strings are hardcoded English, so
the zh/ja/es pricing pages leak untranslated copy (a small pre-existing
i18n gap this spec also closes; the parity guard couldn't see it because
the strings never went through i18n at all).

## Design — `logic/currency.js`

### `CURRENCIES`
`{ USD: {rate 1, roundTo 1}, EUR: {rate 0.92, roundTo 1},
JPY: {rate 155, roundTo 100}, CNY: {rate 7.25, roundTo 10} }`
- **Pegged demo rates** — deterministic and testable. Production pulls
  live rates server-side; the rounding/formatting logic is what this
  module owns permanently. (Documented, not hidden.)
- `roundTo` encodes **psychological price rounding** per market: JPY
  quotes in hundreds (¥77,300, never ¥77,345), CNY in tens, USD/EUR in
  units. This is pricing practice, not math convenience.

### API
- `convertPrice(usd, code)` → `round(usd × rate / roundTo) × roundTo`;
  `0 → 0`; unknown code throws (a pricing page must fail loudly, not
  show a wrong number).
- `formatPrice(usd, code, locale)` → converted amount through
  `Intl.NumberFormat(locale, { style:'currency', currency, maximumFractionDigits: 0 })`.
- `defaultCurrencyFor(locale)` → en→USD · es→EUR · ja→JPY · zh→CNY;
  unknown locale → USD.

## Design — `Pricing.vue`
- Currency pill selector (USD/EUR/JPY/CNY) beside the billing-cycle
  toggle; initialized from `defaultCurrencyFor(locale)`, reactive to
  locale switch until the user overrides manually.
- `Free` / `Custom` become `pricing.free` / `pricing.custom` i18n keys.
- FX note `pricing.fx` ("Prices shown in {code} at a reference rate;
  billed in USD.") ×4 — honest about the peg, standard practice.

## Test plan
- Conversion: fixture math — Growth $499 → ¥77,300 (rounded to 100),
  CN¥3,620 (to 10), €459 (to 1); yearly $399 likewise; 0 → 0; unknown
  code throws.
- Formatting: symbol + no decimals per locale (¥, €, US$); JPY renders
  without fraction digits.
- Defaults: each locale maps as specified; unknown → USD.
- Browser: ja locale defaults to JPY showing ¥77,300; manual switch to
  EUR shows €459; zh shows CN¥3,620 and localized 免费/定制 strings.

## Review record — R1
- ✅ Rounding rules live in the currency table, not the view — each new
  market added in one line, tested in one assertion.
- ✅ Unknown currency throws rather than falling back — silently wrong
  prices are the worst pricing-page failure mode.
- ✅ Free/Custom i18n fix folded in: the gap class (strings bypassing
  i18n entirely) is invisible to the parity gate by construction, so the
  review checklist now includes "no user-facing literal strings in
  views" as a manual review item.
- Verdict: **approved**.
