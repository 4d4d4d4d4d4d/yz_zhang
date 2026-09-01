# Spec 61 — Compliance Posture: a score that survives being read

**Status:** Accepted · **Depends on:** 52 (risk appetite), 57 (i18n ratchet), 60 (markets section)

## 1. Problem (critical analysis)

`TrustCenter` is the surface a buyer is shown to prove the company is safe to
transact with. Its headline number was:

```js
const overall = computed(() => Math.round(
  filtered.value.reduce((s, f) => s + f.score, 0) / filtered.value.length))
```

A plain mean over whatever the region filter let through. That single line
carries three independent defects, and the region filter adds a fourth:

**(a) Unweighted.** GDPR covers 142 controls and C2PA provenance covers 12, and
the mean gave them equal say. Control-weighting moves the headline by up to 8
points — and the direction is not uniform (EU rises, Brazil falls), which is
exactly why it cannot be waved away as a rounding difference.

**(b) Scope-blind.** `filtered` admitted `region === 'all'` frameworks into
every regional view. Selecting Brazil averaged LGPD (78, `warn`) with C2PA
(100) and reported **89** — so the only market flagged for caution read as the
second-healthiest in the estate. The filter made the worst market look better,
which is the opposite of what a filter is for.

**(c) A material exception averaged away.** The EU AI Act framework sits at 64
with `risk` status inside an EU headline of 85. Every audit convention that
exists refuses this: a SOC 2 opinion is qualified by one material exception, an
ISO 27001 major nonconformity blocks certification, CVSS environmental scoring
does not let a critical dissolve into its neighbours. It is also the rule this
codebase already applies to launch blockers in spec 60's `goLive.js` — and
`TrustCenter` was doing the opposite three tabs away.

**(d) The legend never filtered.** The pass/caution/risk counts read from
`frameworks`, not `filtered`, so selecting Brazil printed "5 passing, 2
caution, 1 at risk" — the whole world — directly beside a score labelled `BR`.

Two more, found while fixing those:

**(e) Open risks were decoration.** Five findings, two of them high severity
and naming the exact frameworks in the grid above, sat in a table beside a
score that did not know they existed. A posture that ignores its own open
findings is a snapshot of the last audit, not of today.

**(f) The "AI risk review" was a fixed sentence set.** It returned `score: 78`
and the same five findings on every run regardless of region, filter or state —
the same defect class as spec 58's CPQ margin alert, except here the inputs to
compute it honestly were already on screen.

And the cross-surface consequence: **spec 60 shipped `markets/readiness` last
batch, so the console now had two surfaces answering "is this market ready?"
with unrelated numbers** and no relationship between them.

## 2. Scope

**`src/logic/posture.js`** (new engine)
- `weightedScore` — control-weighted mean; frameworks with no control surface
  are ignored rather than counted as zero.
- `worstOf` / `counts` — scoped, with status ties broken on the lower score.
- `STATUS_CAP = { pass: 100, warn: 84, risk: 69 }` — a material exception caps
  the headline. A ceiling, not a multiplier: the number degrades, it does not
  collapse.
- `deductionsFor` — open findings deduct (high 6 / med 3 / low 1), bounded at
  `MAX_DEDUCTION = 15` so a long tail cannot drive posture to zero.
- `posture(frameworks, { scope, risks, globalScope })` — the full report:
  score, raw, cap, whether it capped, the deduction, scoped counts, and
  per-framework weight shares.
- `MARKET_SCOPE` / `postureForMarket` — resolve a market through its
  regulatory regime.

**`TrustCenter.vue`** — rewired onto the engine, every adjustment shown, the
scan derived, and fully migrated to four locales (17 → 0 hardcoded strings,
ratchet **712 → 695**).

**`MarketReadiness.vue`** — reads the same engine, so `trust/posture` and
`markets/readiness` cannot disagree about a market.

## 3. What the numbers became

| scope | shipped | now | why |
|---|---:|---:|---|
| All | 87 | **54** | weighted 88, capped 69 by AI Act, −15 findings (bounded) |
| EU | 85 | **60** | weighted 88, capped 69 by AI Act, −9 findings |
| US | 97 | **91** | weighted 94, −3 |
| JP | 96 | **91** | weighted 92, −1 |
| BR | 89 | **72** | weighted 78 (was 89 with C2PA folded in), −6 |
| SEA | 95 | **89** | weighted 89, nothing outstanding |

Every score fell, several sharply. That is the finding, not a side effect: the
old number was flattering because it averaged a material exception away, let
global coverage stand in for regional coverage, and ignored its own open
findings. The panel now shows each step — control-weighted, cap, deduction —
so the number is arguable rather than asserted.

## 4. Review record

**R1 — the estate cap is deliberate and conservative.** Capping the *all
regions* headline at 69 because one EU framework is at `risk` is a strong
claim, and it is the one group-audit convention makes: an opinion is qualified
if any material component is. The alternative — letting a healthy majority
absorb it — is precisely the behaviour being removed. The panel names the
framework doing the capping, so the judgement is visible and contestable.

**R2 — a cap, not a multiplier.** Multiplying by a status factor would make the
number unreadable (what does 0.7× mean?) and would punish a large clean estate
for one small exception twice over. A ceiling degrades the claim to "no better
than this" and leaves the underlying weighted score on screen beside it.

**R3 — global coverage is reported, not counted.** C2PA applies everywhere and
deleting it from regional views would hide real coverage. It is rendered in the
grid with a dashed border and a "not counted in this region" tag, and excluded
from the arithmetic. Both halves are tested.

**R4 — deductions are bounded, and the bound is disclosed.** Forty low-severity
findings should not read as an emergency, so the deduction stops at 15. When it
binds, the scan says so explicitly ("open findings total N points; the
deduction is bounded at 15") rather than silently discarding the excess.

**R5 — my own coverage gap found a design hole.** Branch coverage came in at
74%, and chasing the uncovered lines surfaced a case I had not thought about:
frameworks that exist but declare **zero** controls scored **0**. That reads as
a failed audit when the truth is an absent one — the same lie-of-omission the
uncovered-scope path was written to avoid. Both now return `covered: false`
with a distinguishable `reason` (`no-regime` vs `no-controls`), and the
uncovered report keeps the full shape so no consumer has to branch on it.
Branch coverage 74% → **95.8%**, with tests that assert behaviour rather than
touch lines.

**R6 — the scan reuses the panel's own engine.** Deriving it from a second
code path would just create a new way for two numbers on one screen to
disagree. It renders the posture's own cap, its own scoped findings and its own
bounded deduction, and a test asserts the scan score equals the headline for
every region.

**R7 — one answer per question, across surfaces.** `postureForMarket` maps
market → regime (`DE → EU`, `ID → SEA`), and a browser check confirms
`trust/posture` at EU and `markets/readiness` for Germany both read 60 in all
four locales. A market with no regime in scope (`AE`, `MX`) says "coverage is
unknown, not clean" instead of rendering a comfortable number — the same
honest-absence rule as R5.

**R8 — hostile input is exercised, not assumed.** Framework and finding rows
come from a register people edit by hand, so null rows, unknown statuses,
missing keys and non-array inputs each have a test rather than a hopeful `?.`.

## 5. Tests

- `tests/posture.test.js` (35) — weighting; the Brazil scope regression pinned
  against the shipped mean (89) and the corrected value (78); the cap on EU;
  cap as ceiling not penalty; tie-breaks; scoped deductions and the bound;
  never negative; scoped counts; contributions summing to 1; both absence
  reasons; per-market resolution; hostile input.
- `tests/trustCenter.test.js` (17) — the region filter isolates; the global
  framework is shown but tagged and excluded; the legend counts the region; the
  cap line appears only when it binds; the headline matches the engine for
  **every** region; the scan agrees with the headline and moves with the
  region; cross-surface agreement with `MarketReadiness`; uncovered markets;
  four-locale rendering with an unresolved-key check.

Teeth-verified, each restored immediately: reinstating the unweighted mean
fails the weighting test; folding global frameworks back into regional scope
fails **10** tests; removing the material-exception cap fails the EU cap test;
restoring the hardcoded `score: 78` fails the derived-scan test.

## 6. Gate

`npm run test:coverage` — **966 tests across 69 files** (was 909/67), functions
100%, statements/lines 99.85%, branches 93.7%; `posture.js` at 95.8% branch.
`npm run build` clean. `npm run check:bundle` — console path 110.4 KB (budget
130), landing 86.5 (110), total 265.1 (285).

Browser-verified: posture recomputed across all six regions with the calculation
shown; the scan returning 60 for EU (naming the AI Act cap and both EU
findings) and 91 for JP (its single low finding); and `trust/posture` EU ==
`markets/readiness` Germany == 60 in en / zh / ja / es.

## 7. Note on the container

The session container reset to the base commit mid-batch for the second time
(the first was during spec 42). Every pushed commit was intact on the remote;
the branch was restored with `git checkout -B` from origin, dependencies
reinstalled, and the two in-flight files recovered from the scratchpad. Nothing
was lost, and it is the reason specs are pushed per batch rather than batched
up.
