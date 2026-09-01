# Spec 58 — Locale Code-Splitting, and the CPQ Surface That Lied

**Status:** Accepted · **Depends on:** 15 (CPQ engine), 28 (bundle budget), 57 (i18n debt ratchet)

## 1. Problem (critical analysis)

Three problems, and the third only became visible because of the first two.

**(a) Two more components of i18n debt.** Spec 57 measured 779 hardcoded
English strings and made the number a CI ratchet. The two worst offenders were
`RiskHeatmap` (35) and `CPQEditor` (32) — both operator surfaces on the path to
signing a deal, both English-only in a product sold on going global.

**(b) The quality guard was fighting the performance guard.** Every locale was
imported eagerly into `src/i18n/index.js`, so all four message trees landed in
the entry chunk. Migrating `CPQEditor` pushed that chunk to **100.59 KB gzip
against a 100 KB budget**, and `check:bundle` failed. This is the important
finding: under the old bootstrap, *every* i18n migration made the first paint
heavier, so spec 57's ratchet and spec 28's budget were pulling in opposite
directions. Raising the budget would have been the wrong fix — it would have
paid for correctness in bytes forever, and 68 components still remain.

**(c) `CPQEditor` was making claims it did not compute.** Reading it closely
during the migration turned up three defects:

1. **The "AI" margin alert was a fixed sentence.** *"Margin below floor (50%).
   Consider trimming GPU bundle discount to 4% to restore margin to 52%."* It
   named the same product and the same two numbers no matter what the rep had
   configured. Worse, its `v-if` fires below 50% blended margin, which the
   default quote never reaches — so the only thing it ever did was mislead
   whoever *did* discount their way into it.
2. **The approval marker sat in the wrong band.** The bar draws four
   equal-width columns for tiers spanning 0–5 / 5–15 / 15–25 / 25+. The marker
   was positioned at `discount * 3`. At **8% blended discount the marker
   rendered at 24% — inside the "Auto" column — while the heading directly
   above it read "Sales Manager."** Two elements, six inches apart, disagreeing
   about who has to sign off on the deal.
3. **The zone captions were a hardcoded copy of the thresholds.** `data-z="0–5%"`
   and friends were typed into the template, independent of `approvalFor`'s
   comparisons. Move a threshold and the bar keeps illustrating the old policy.

Underneath all three: `approvalFor` returned English display copy (`level`,
`who`) from the pure-logic layer, which makes the tier untranslatable by
construction.

## 2. Scope

**Locale code-splitting** — `src/i18n/index.js`:
- Only the fallback locale `en` is bundled. `zh`/`ja`/`es` are `import()`ed on
  demand and cached; concurrent requests share one fetch.
- `setLocale` is async and returns success — a failed chunk leaves the reader
  on their current locale rather than a blank UI.
- New `bootstrapI18n()`, awaited in `main.js` before mount, so a saved
  non-English preference never flashes English on the way in.
- `localStorage` access is wrapped in both directions (private mode throws on
  read *and* write).

**`src/logic/cpq.js`**:
- `APPROVAL_TIERS` — the single tier table (`key`, `to`, `color`).
- `approvalFor` returns a **key**, not copy.
- `markerPercent` — piecewise map from discount to bar geometry.
- `marginRecovery(quote, floorPct, step)` — solves the real recommendation.

**`src/components/{RiskHeatmap,CPQEditor}.vue`** — fully migrated to `t()` in
four locales (`riskmap.*`, `cpq.*`); ratchet lowered **779 → 744 → 712**.

## 3. The margin-recovery derivation

Blended margin is `(N − C) / N`. Trimming a line's discount raises net and
leaves cost untouched, so to reach floor `f`:

```
(N + Δ − C) / (N + Δ) = f   ⟹   N + Δ = C / (1 − f)   ⟹   Δ = C/(1−f) − N
```

Δ is **independent of which line supplies it** — every feasible line costs the
buyer exactly the same dollars. What differs is headroom: line *i* can supply
at most `gross_i × discount_i / 100`. So the recommendation picks among
feasible lines by *defensibility*: trim the deepest discount first, ties broken
by gross. The suggested discount is rounded **down** to the step so the rep who
types it lands at or above the floor, never a hair under it.

When no single line has the headroom, the panel says so and reports the gap
instead of inventing a fix it cannot deliver.

## 4. Review record

**R1 — the budget failure was the finding, not the obstacle.** The honest read
of `100.59 KB > 100 KB` was not "the budget is too tight"; it was "the
bootstrap makes localization cost the entry chunk." Code-splitting took the
entry chunk from **100.59 → 82.02 KB gzip** and, more importantly, made every
future migration cost bytes only in the locale the reader actually requested.
Two guards that were fighting now pull the same way.

**R2 — `en` stays bundled on purpose.** It is the `fallbackLocale`. Lazy-loading
it too would mean a missing key in a slow-loading locale renders as a raw key
path. One eagerly-bundled locale is the price of never showing `cpq.lineItems`
to a customer.

**R3 — logic must not emit English.** `approvalFor` used to return
`'Sales Manager'`. No amount of template work can translate a string the engine
manufactured. It now returns `key: 'manager'`, and a test asserts the returned
object has no `level`/`who` properties at all — so the regression can't creep
back as a "convenience" field.

**R4 — the marker bug is verified against the old formula.** The test doesn't
just assert the new positions are right; it asserts `8 * 3 < 25` (the old
formula really did land inside "Auto") and then that `markerPercent(8) > 25`.
Teeth-verified by restoring `Math.min(95, blendedDisc * 3)` in the template,
which fails the mount test.

**R5 — a hard-coded "AI" recommendation is worse than none.** A static sentence
dressed in an `AI` badge is a claim about analysis that never happened. It is
the same defect class as specs 46–54, and the fix is the same: compute it, or
delete the claim. Here the arithmetic exists, so the test applies the advice
back through `priceQuote` and asserts the resulting margin matches what the
alert promised — the sentence is checkable, not decorative.

**R6 — my own test asserted the wrong thing twice.** First, the tie-break case
used a floor the fixture already cleared, so `marginRecovery` correctly returned
`null` and the test read it as a failure of the engine. Second, the
"doesn't say 4%" assertion failed against the *correct* output `56.4%` — a
substring check masquerading as a semantic one. Both were my errors; the
replacements assert that both candidate lines have enough headroom (so the
choice is genuinely the tie-break) and that the alert no longer names the GPU
bundle.

**R7 — no vacuous branches in tests.** A first draft of the shortfall test had
an `if (alert.exists())` fallback that would have passed either way. Deleted;
the infeasible path is covered where it can be constructed deterministically —
in the pure-logic test.

**R8 — the zone captions are derived.** `zones` computes each range from
`APPROVAL_TIERS`, so the copy under the bar cannot drift from the comparisons
that route the approval. A test pins the rendered `data-z` values against the
table.

**R9 — currency formatting follows the reader.** `Intl.NumberFormat` now takes
`locale.value` rather than a hardcoded `'en'`, and the old `${{ ... }}` string
concatenation is gone. Browser-verified: `$2,160` / `US$2,160` / `2160 US$`
across locales — correct per-locale placement, not a glued-on dollar sign.

## 5. Tests

- `tests/quoteToCash.test.js` — +5 cases: tier keys and boundary values,
  garbage input, marker containment and monotonicity, the four
  `marginRecovery` paths (silent / feasible / tie-break / shortfall), zero-net
  and 100%-floor safety.
- `tests/cpqEditor.test.js` (new, 10 cases) — mounts the real component:
  zones derived from the table, marker and heading agreeing across the tier
  range, the alert absent above the floor and *named and moving* below it, and
  four-locale rendering with an English-leakage check.
- `tests/localeLoader.test.js` (new, 12 cases) — only `en` bundled; on-demand
  fetch; persistence; navigator fallback; saved preference outranking it;
  unsupported locale rejected; shared in-flight fetch; blocked storage;
  `document.documentElement.lang`; and every offered locale actually loadable.
- `tests/i18n.debt.test.js` — budget lowered to **712**; `RiskHeatmap.vue` and
  `CPQEditor.vue` added to `MIGRATED` (must stay at zero).

Teeth-verified, each restored immediately: the linear marker formula fails the
mount test; one hardcoded string in `CPQEditor` fails the ratchet; a deleted
`zh` key fails locale parity *and* the component locale test; a hardcoded
`toDiscount = 4` fails the recovery test.

## 6. Gate

`npm run test:coverage` — **787 tests across 62 files**, functions 100%,
statements/lines 99.82%, branches 93.43%. `npm run build` clean.
`npm run check:bundle` — all chunks within budget, entry chunk **82.02 KB**
(was 100.59, budget 100), total 230.7 / 250.

Browser-verified at `/console/deals?sub=cpq` and `/console/trust?sub=heatmap`
in all four locales: locale chunks fetch with 200 (none for `en`, as intended),
`html[lang]` tracks the locale, the approval bar renders four zones with
derived ranges, and the margin alert reads —

> Margin 48.6% is below the 50% floor. Trim Platform · Enterprise from 60.0% to
> 56.4% — adds $2,160 of net and restores margin to 50.0%.

— naming the line the rep actually discounted, not the GPU bundle.

## 7. Remaining

712 strings across 69 components. Worst offenders: `MarketingControl` (25),
`FeatureStore` (24), `NegotiationPlaybook` (24), `TrustPipeline` (22),
`ControlsRegister` (21), `MarketplaceCommission` (21), `PersonalizationDash`
(21). Each migration now costs the entry chunk nothing.
