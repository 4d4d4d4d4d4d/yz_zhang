# Spec 47 — Sales Forecast (double-count fix + pipeline coverage)

**Status:** Accepted · **Depends on:** partners surface (spec 03 lineage)

## 1. Problem (critical analysis)

`SalesForecast` computed quota attainment as `closedWon + commit`. But forecast
categories are a **partition**: a Closed Won deal is *already* in the commit
category. In the shipped dataset D-2842 ($1.2M) is both, so it was counted
twice:

| | shipped | correct |
|---|---|---|
| Attainment | **77%** | **49%** |
| Gap to quota | **$960k** | **$2,160k** |

That is not cosmetic. **It inverted the forecast health signal**: with the
understated $960k gap, the $3,815k open pipeline implies ~4.0× coverage
(healthy); against the true $2,160k gap it is **1.8×** — well under the
industry 3× rule, i.e. a quarter genuinely at risk. A sales leader reading the
old screen would have stood down instead of building pipeline.

Two smaller defects rode along: the stage ladder listed Proposal (0.55) above
Negotiation (0.65), so the funnel rendered out of order; and the attainment bar
stacked `closedWon + commit + best`, painting the banked revenue twice.

Pipeline coverage — the single most-used forecasting metric — was absent.

## 2. Scope

- `logic/salesForecast.js` — pure: `DEFAULT_STAGES` (ordered ladder with win
  probabilities), `stageWeight`, `weightedPipeline`, `categoryTotals`
  (partition; unknown categories ignored, not folded), `closedWonTotal`,
  `openPipeline`, `coverageRatio`, `auditCategories` (forecast hygiene), and
  `forecastSummary` returning the full roll-up with **committed = commit**
  (never `closedWon + commit`), nested `bestCase`/`allIn`, attainment, gap,
  coverage, and a `coverageHealthy` flag against the 3× benchmark.
- `SalesForecast.vue` — consumes the engine; stages display high→low in true
  ladder order; the attainment bar stacks `closedWon` + *open* commit + best;
  a new **pipeline coverage** readout shows `x.x× vs 3× benchmark`.

## 3. Review record

**R1 — categories are a partition, and the code must say so.** The fix is not
"subtract the overlap"; it is to stop treating `closedWon` as additive at all.
`committed` is the commit category, full stop. Two regression tests pin this,
including `expect(s.committed).not.toBe(s.closedWon + s.commit)`.

**R2 — coverage is null, not Infinity, once the gap closes.** Dividing by a
zero gap is meaningless rather than infinitely good; `coverageRatio` returns
`null` and the UI renders "—", while `coverageHealthy` stays true (quota met).

**R3 — surface bad data, don't silently repair it.** `auditCategories` flags a
Closed Won deal that isn't in commit rather than reassigning it, so a broken
CRM export is visible instead of quietly changing the number.

## 4. Tests
`tests/salesForecast.test.js` (17), including a dedicated **REGRESSION** block
asserting attainment 49% (not 77%) and gap $2.16M (not $960k) on the exact
shipped dataset; plus ladder ordering, unknown-stage → 0 weight, category
partition, `commit ⊆ bestCase ⊆ allIn` nesting, open pipeline excluding Closed
Won, coverage math and null-on-closed-gap, the hygiene audit, and empty-input
guards.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: attainment renders 49%, gap $2,160k, coverage
"1.8× vs 3× benchmark", and the funnel lists Negotiation above Proposal.
