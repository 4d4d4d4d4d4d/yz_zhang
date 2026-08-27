# Spec 57 — i18n Debt Ratchet + First Migrated Console Module

**Status:** Accepted · **Depends on:** 14 (i18n completeness), 33 (staged migration precedent)

## 1. Problem (critical analysis)

The product's entire thesis is 出海 — going global — and it ships four locales
with a parity-enforced key tree. But the parity test guards the *locale files*,
not the *components*. A measurement across `src/components` and `src/views`
found **779 hardcoded user-visible English strings across 72 components**.

So the marketing site localizes cleanly while the console — the thing actually
being sold — is English-only. That is the same claims-versus-reality gap this
series has been closing all along, and it is the largest one left.

It is also not fixable in one batch: 779 strings × 3 additional locales is
~2,300 translations. Pretending otherwise would produce a half-migrated console,
which is worse than an honestly-scoped one.

## 2. Scope

Following the staged-migration precedent of specs 13 and 33:

- `tests/i18n.debt.test.js` — a **ratchet**, modelled on the bundle budget:
  - `TOTAL_BUDGET = 779` — the measured debt. It may be lowered as components
    migrate; raising it is the thing the guard exists to prevent.
  - `MIGRATED = ['UsageMetering.vue']` — components declared done must stay at
    **zero**. Adding one English string to a migrated component fails outright,
    independently of the total.
  - The failure message names the worst offenders, so the next migration target
    is obvious without re-writing the measurement script.
- **`UsageMetering.vue` fully migrated** — 25 keys under `metering.*` authored
  in all four locales, including interpolated forms (`invoiceTitle`,
  `platformFee`, `optCacheBody`) so grammar stays natural rather than
  concatenated.

## 3. Review record

**R1 — a ratchet, not a target.** A "TODO: localize the console" comment
changes nothing. A budget that CI enforces makes the debt visible, blocks
growth, and turns each migration into a measurable decrement. This is exactly
how the bundle budget (spec 28) has kept chunk size honest.

**R2 — two independent assertions.** The total can only fall; a migrated file
must be exactly zero. Without the second, a component could be declared "done"
and quietly regress while the total still passed on someone else's migration.
Teeth-verified: one added string fails **both**.

**R3 — the guard's own false positive, caught and fixed.** The first version
flagged `:title="t('metering.proRata')"` as debt, because a bound attribute
still ends in `title=`. A guard that punishes correct localization would push
people away from the fix. A lookbehind now excludes bound attributes.

**R4 — the measurement got stricter, and the number went up.** My first probe
used a non-greedy `</template>` match that truncated components containing
`<template v-for>` blocks, under-reporting the debt as 803 before migration.
The corrected scanner is the one shipped. The honest number is higher than the
first estimate.

**R5 — interpolation over concatenation.** `invoiceTitle: 'Current invoice ·
day {day} of {days}'` keeps word order translatable; gluing fragments together
produces sentences that cannot be rendered correctly in Japanese or Spanish.

## 4. Tests
`tests/i18n.debt.test.js` — the ratchet plus the per-migrated-file check.
Teeth-verified by inserting one hardcoded string into `UsageMetering`, which
fails both assertions; restored immediately.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget. 753 tests across 60 files. Browser-verified: the metering module
renders correctly in all four locales — "Metered billing · Stripe-style" /
"按量计费 · Stripe 模式" / "従量課金 · Stripe スタイル" / "Facturación por uso ·
estilo Stripe".

## 6. Remaining
778 strings across 71 components. Worst offenders at time of writing:
`RiskHeatmap` (36), `CPQEditor` (32), `MarketingControl` (25),
`NegotiationPlaybook` (25), `FeatureStore` (24). Each migration lowers
`TOTAL_BUDGET` by exactly its count.
