# Spec 60 — Market Expansion: a new console section

**Status:** Accepted · **Depends on:** 20 (section registry), 57 (i18n ratchet), 59 (section code-splitting)

## 1. Why this, and why now

Direct feedback on the work: specs 55–59 shipped five consecutive batches of
guards, budgets, i18n and code-splitting, and **zero new user-facing
capability**. That criticism is correct. Nothing was removed — `git log
--diff-filter=D` over `src/components` and `src/logic` shows no deletions, and
the panel count never dropped — but "did not delete" is not "added". This spec
is the correction: the batch is purely additive.

The gap it fills is the most upstream one in the product. Seven console
sections cover recommendations, marketing, partners, deals, showcase,
immersive and trust — and every one of them **assumes the market has already
been chosen**. For a product whose entire thesis is 出海, the four questions
that come first had no home anywhere:

1. Which market do we enter next?
2. What do we charge there once duty, VAT and local payment fees are real?
3. Can we legally transact there yet?
4. What do we have to start *today* to make the dates that cannot move?

## 2. Scope

New section `markets` (🌍), four panels, four engines, four locales.

**`src/logic/marketEntry.js`** — attractiveness (GE–McKinsey style) and CAGE
distance (Ghemawat 2001) scored **separately**, then combined with a friction
ceiling. Explainable contributions, entry bands, and margin-aware payback.

**`src/logic/landedCost.js`** — CIF-based duty, a price solved backwards from
target margin, and market-specific charm rounding.

**`src/logic/goLive.js`** — blocking vs advisory gates, critical path, earliest
realistic launch date.

**`src/logic/retailMoments.js`** — backward lead-time planning from immovable
retail dates.

**Panels** — `MarketEntryScorer`, `LandedCostPricer`, `MarketReadiness`,
`RetailCalendar`, shipped as the `markets` chunk (8.2 KB gzip).

Registry entry, section barrel, `g x` keyboard shortcut, and ~115 keys per
locale across `market.*`, `entry.*`, `landed.*`, `golive.*`, `moments.*`.

## 3. The arithmetic worth stating

**Price from target margin.** The naive `cost / (1 − margin)` is wrong whenever
a payment fee exists, because the fee scales with the price you are solving
for:

```
gross         = P·(1+v)                 shown to the buyer
remitted VAT  = P·v
processor fee = P·(1+v)·f               charged on the gross
net to us     = P·(1 − (1+v)·f)
margin m      = (net − landed)/net  ⇒  net = landed/(1−m)
⇒ P = landed / [ (1−m)·(1 − (1+v)·f) ]
```

VAT is collected and remitted, so it never enters the margin numerator — but it
*does* enlarge the base the processor charges on, which is why the price must
be solved rather than marked up. A test ships the naive price through the same
money flow and shows it landing under target.

**Duty on CIF, not FOB.** Duty is assessed on goods + freight + insurance.
Applying it to the ex-works price alone understates every landed cost
downstream — pinned by a test where the difference is 12.50 vs 10.00.

**Backward planning.** Retail dates do not move. Planning forward from today is
how they get missed; the only correct direction is backward from the date
through each production stage to the latest safe start. If that start is behind
you, the campaign is late **today** — which a calendar of coloured pills never
tells you.

## 4. Review record

**R1 — attractiveness and distance stay apart.** Most "which market next"
dashboards collapse them into one number, which hides the case that matters: a
huge, fast-growing market you are structurally unequipped to serve. Kept
separate, the panel can say Brazil is attractive *and* administratively
expensive, and name which CAGE barrier dominates. A test asserts a maximally
distant market keeps its attractiveness score untouched.

**R2 — friction is decisive, not fatal.** A ceiling of 0.55 means the hardest
imaginable market loses 55% of its prize, not 100%. Japan is distant from
almost everywhere and people still sell there. The ceiling is a slider, and a
test shows that moving it to zero flips the ranking to the biggest market —
proof the control feeds the engine rather than decorating it.

**R3 — blocking gates withhold; they do not average.** A percentage that blends
"VAT registration filed" with "help centre translated" produces a comfortable
85% next to a market that legally cannot take an order. Blocking and advisory
completeness are two numbers, side by side, and the panel says so in as many
words. Tested with a market at 100% advisory and one open blocker.

**R4 — critical path is the longest pole, not the sum.** Remediation runs in
parallel across different owners: 10 + 25 + 7 days of open gates is 25 days,
not 42. The panel also names the owner of the longest pole, because "who do I
chase" is the actual question.

**R5 — the browser check caught a defect the unit tests could not.** Charm
conventions are denominated in the currency the shopper sees: `end90` means
¥2,990, not $29.90. The first implementation rounded the **USD** price and
converted afterwards, landing on a number that is a charm price in neither
currency. On the JP row it inflated margin from the 58% target to **69.2%** —
plausible-looking, entirely wrong. `applyCharm` now takes the rate and rounds
in local currency; the same row reports 58.0% against a ¥32,290 shelf price,
and a test pins both the correct behaviour and the size of the old error.

**R6 — two dead branches in my own panels, found by tests that failed
honestly.** The pricing panel capped target margin at 95%, so its "target
unreachable" message could never render; the cap is now 100, which is exactly
where no finite price exists, and the message earns its place. The calendar
fixture had nothing late, so the "what is behind today" alert — the panel's
entire reason to exist over a calendar widget — never appeared; two real
near-term moments (Fiestas Patrias, Oktoberfest) now exercise it.

**R7 — the guards caught the coupled surfaces, as designed.** Adding a section
failed two existing tests immediately: the `g`-goto map no longer covered every
console section (fixed with `g x`, `m` being taken by marketing), and a
prefetch test asserted a hardcoded sidebar neighbour. The second was rewritten
to derive neighbours from the live registry, so inserting a section can never
again make that assertion quietly describe a sidebar that no longer exists.

**R8 — the i18n ratchet did its job without being invoked.** Debt stayed at
712 across the whole batch: four new panels shipped fully localized because
hardcoded English would have failed CI. New features are now localized by
construction rather than by discipline.

**R9 — the total bundle budget was raised, and that is the correct call
here.** A new section pushed the sum of all chunks from 258.3 past 250. Spec 59
demoted that sum to a coarse anti-bloat ceiling precisely because nobody
downloads it; the metric that describes a reader — the console path — moved
from 106.9 to **109.2 KB against a 130 budget**, because the `markets` chunk
(8.2 KB) is not the heaviest section. Total raised to 285, with the rule now
written into the source: raising TOTAL while a *path* budget also rises is the
signal to stop and split something. A test pins the distinction.

## 5. Tests

- `tests/marketEntry.test.js` (16) — the two frames stay separate; contributions
  sum to the score; band boundaries; descending band table; margin-aware
  payback returning `null` rather than `Infinity`; re-weighting flips the
  ranking; clamping, junk input, deterministic tie-breaks.
- `tests/landedCost.test.js` (19) — duty on CIF; the solved price hits target
  exactly while the naive formula undershoots; VAT out of the numerator;
  unreachable targets return `null`; charm rounds *up* on every declared
  convention; charm in local currency, with the old USD error's magnitude
  pinned; rate fallbacks.
- `tests/goLive.test.js` (19) — blockers withhold regardless of polish;
  weighted advisory; longest pole not sum; ranking puts every live-able market
  above every blocked one; plus the backward-planning suite (stage chaining,
  late-today, passed vs late, horizon as a parameter, `atRisk` subset).
- `tests/marketsSection.test.js` (24) — registry/shortcut/locale wiring, and
  each panel driven through its real controls: sliders move the ranking, the
  reset button appears only after a change, raising target margin moves every
  price, charm only ever helps margin, blocked markets name their blockers,
  the horizon control filters, and all four panels render in all four locales
  with an unresolved-key check.

`prefetch.js` and the four new engines are at 100% function coverage.

## 6. Gate

`npm run test:coverage` — **909 tests across 67 files** (was 813/63), functions
100%, statements/lines 99.84%, branches 93.59%. `npm run build` clean.
`npm run check:bundle` — `markets` 8.2 KB (ceiling 22), console path 109.2 KB
(budget 130), landing 85.4 KB (budget 110), total 258.4 (budget 285).

Browser-verified at `/console/markets?sub={entry,landed,readiness,calendar}` in
en / zh / ja / es: every panel renders, no unresolved keys, no console errors,
currency and dates formatted per locale — `¥32,290` / `US$77.88` / `77,88 US$`
/ `IDR 3,687,900` — and the pricing ladder lands on 58.0–58.2% across all six
markets against a 58% target.

## 7. Not done

The section ships with fixture data, like every other console section in this
codebase. The engines are the deliverable and they are real; wiring them to a
live market-data source is a separate piece of work with a separate spec.
