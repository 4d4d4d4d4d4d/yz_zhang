# Spec 33 — Locale-Aware Figure Formatting (staged)

**Status:** Accepted · **Depends on:** 13 (migration policy), 25 (currency)

## 1. Problem (critical analysis)

A grep of the console found **60+ figures across ~20 components** rendered
with hardcoded `${{ …toLocaleString() }}` / `.toFixed()`. Two concrete
defects follow from this:

1. **Locale-incorrect grouping.** `toLocaleString()` with no locale argument
   uses the *runtime's* locale, not the operator's. A JP/ES operator on the
   same build sees US grouping — a credibility problem for a go-global product.
2. **A real display bug.** `RevenueDashboard.vue` rendered ARPU as
   `$${{ … }}` — a literal double dollar (`$$3,986`).

The fix is a single locale-aware formatting layer that reads the operator's
i18n locale, plus a staged migration of the surfaces onto it.

## 2. Scope

- `logic/format.js` — pure Intl wrappers, deterministic given (value, locale):
  `num` (grouped), `compact` (1.2K/3.4M), `money` (currency, optional compact),
  `pct` (fraction → percentage). Non-finite input renders `—`, never `NaN`/`$NaN`.
- `composables/useFormat.js` — binds those to the live i18n locale so a
  component writes `money(x)` and never touches Intl or a hardcoded `$`.
- **Flagship adoption:** `RevenueDashboard.vue` fully migrated (every visible
  MRR/ARR/ACV/ARPU/share figure) and the `$$` ARPU bug fixed.

## 3. Migration policy (per spec 13 precedent)

The remaining components migrate incrementally, highest-visibility money
surfaces first (CPQ, metering, commission, marketing revenue), in later
rounds. Rules:
- New components MUST use `useFormat` — no new `toLocaleString()`/`$` literals.
- Base currency stays **USD**; console figures are not FX-converted (that is a
  pricing-surface concern owned by spec 25). `money()` takes a `currency`
  override for the rare non-USD figure.
- Layout-only math (bar heights, cumulative offsets) is not a formatting
  concern and stays as-is.

## 4. Review record

**R1 — currency semantics.** Rejected wiring the spec-25 currency preference
into console figures: those numbers are internal-ops USD, and silently
FX-converting them would misstate revenue. Locale affects *grouping and
notation only*; the currency stays USD unless a caller overrides.

**R2 — `pct` takes a fraction, not points.** Callers pass `0.12`, not `12`.
This removes the ambiguity that produced ad-hoc `* 100` scattered in views and
lets `Intl` own the `%` sign and rounding.

**R3 — em-dash on non-finite.** A dashboard must never surface `NaN`/`$NaN`.
`Number(null)`/`Number('')` coerce to `0`, so the guard rejects nullish/empty
*before* coercion; genuine `0` still formats as `$0`.

## 5. Tests
`tests/format.test.js`: grouping differs across locales, compact suffixes,
USD + currency override, fraction→percent, and the non-finite → `—` guard
(including the `null`/`''` coercion trap). Component wiring covered by the
existing mount-smoke sweep.

## 6. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget, plus a browser check that RevenueDashboard renders `$384K` /
`$3,986 ARPU` (no `$$`) and that switching locale regroups the figures.
