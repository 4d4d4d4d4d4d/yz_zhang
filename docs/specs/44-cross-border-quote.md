# Spec 44 — Cross-Border Quote (partner currency)

**Status:** Accepted · **Depends on:** 15 (CPQ), 25 (currency)

## 1. Problem (critical analysis)

The platform exists to close **cross-border** deals, yet `CPQEditor` quoted
everything in **USD only** — and its sample buyer is "Lumen Studios **K.K.**", a
Japanese entity that thinks in yen. It even carried a `customer.currency` field
that was hardcoded `'USD'` and never used. Every CPQ tool (Salesforce CPQ,
DealHub) shows the buyer their own currency. `currency.js` (spec 25) had the
pegged rates but was only wired to the pricing page.

## 2. Scope

- `logic/quote.js` — pure: `convertAmount(usd, rate)` (whole-unit rounding,
  guarded) and `crossBorderQuote(netUsd, {code, rate})` → the partner-currency
  view with an `isUsd` flag. The rate is **injected** (the component reads it
  from `currency.js`), so the logic layer stays dependency-free.
- `CPQEditor.vue` — a **Buyer currency** picker (USD/EUR/JPY/CNY); the TCV shows
  the partner-currency equivalent beneath it with the pegged FX rate and a
  "billed in USD" disclaimer (consistent with spec 25's model). The sample buyer
  now defaults to JPY.

## 3. Review record

**R1 — inject the rate, don't import.** `logic/quote.js` must not import
`logic/currency.js` (spec 00 §2 / `architecture.test.js`). The component owns the
rate lookup and passes it in, keeping conversion pure and testable.

**R2 — reference, billed in USD.** Following spec 25, the partner amount is a
transparent reference at the pegged rate; billing stays USD. The disclaimer says
so on the quote, so the number is never mistaken for the invoiced amount.

**R3 — no FX noise for USD.** `isUsd` suppresses the conversion line when the
buyer currency is USD, so a US deal reads clean.

## 4. Tests
`tests/quote.test.js`: conversion + rounding + guards, USD passthrough, non-USD
conversion with the `isUsd` flag, and safe defaults. Picker/render covered by
mount-smoke.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: a $157,920 TCV shows ≈ ¥24,477,600 (×155) and
≈ €145,286 (×0.92); USD hides the FX line.
