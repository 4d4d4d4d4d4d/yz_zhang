# Spec 53 — Expansion Score Derived From Its Own Signals

**Status:** Accepted · **Depends on:** 16 (customer success)

## 1. Problem (critical analysis)

`UpsellEngine` presents itself as an "Expansion engine · AI-scored" and shows a
score per account (92, 84, 76, 71, 62). Every one was a **hardcoded literal** —
while each account's `signals` array, complete with per-signal `strength`
ratings, sat immediately beside it unused. The panel headed *"Signals · why
this scored 92"* listed evidence that had no causal relationship to the 92.

Accounts were also ordered by **raw upside**, which is the wrong work queue: it
sends a rep at the biggest number rather than the best opportunity.

## 2. Scope

- `logic/expansion.js` — pure: `SIGNAL_WEIGHTS` over the eight signal types the
  register actually uses, `STRENGTH` (high/med/low), `strongestByTag` (a
  repeated signal type counts once, at its strongest), `expansionScore`,
  `scoreBreakdown` (per-signal contributions, largest first),
  `expectedValue(score, upside)`, and `rankOpportunities`.
- `UpsellEngine.vue` — consumes the engine; the list ranks by expected value and
  shows it; the detail panel gains a score-contribution breakdown and states the
  expected-value arithmetic inline.

## 3. Review record

**R1 — the denominator is the full signal set, deliberately.** Scoring against
only the signals observed would give any account with one strong signal a 100.
Missing evidence should lower confidence, so an account showing 3 of 8 signal
types scores partially. The consequence is honest and worth stating: derived
scores (50, 32, 25, 16, 12) are far below the asserted ones (92, 84, 76, 71,
62), because these accounts genuinely have partial evidence.

**R2 — the UI had to move with the scale.** Leaving the old bands (≥85 high) and
the "pre-draft only when score ≥ 60" copy would have made every account read
"low" and the copy false. Bands were re-cut to the real distribution and the
headline now says what the number means: **evidence coverage**. Changing the
model without changing its presentation would have swapped one incoherence for
another.

**R3 — rank by expected value, not score or upside.** Northwave carries the
largest upside ($6,800) but weak evidence (25), so it ranks *below* Lumi
($4,200 at 50). Kaito scores higher than Northwave (32 vs 25) yet ranks below it,
because expected value — not either input alone — is what orders a rep's day.

**R4 — the two extra signal types were added, not discarded.** The register uses
`client` and `integration` tags; rather than let unknown tags silently score 0
and crater those accounts, both were given weights with a stated rationale.

## 4. Tests
`tests/expansion.test.js` (17): full marks only at complete high-strength
coverage, zero with no signals, monotonicity in strength, non-uniform weights
(intent > health), no double-counting a repeated type, strongest-wins on
repeats, unknown tags and malformed strengths ignored, partial coverage scoring
partially; breakdown ordering and contributions summing to the score; expected
value and its guards; and ranking that puts a well-evidenced smaller
opportunity above a poorly-evidenced larger one, overwrites any asserted score,
and is deterministic on ties.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget, plus a browser smoke: the list ranks Lumi $2,100 → Northwave
$1,700 → Kaito $512 → Aurora $288 → Cobalt $128 (weighted pipeline $4,728);
Lumi's breakdown reads Intent 24.0 + Usage 22.0 + Feature 3.6 ≈ 50, and the
note states "$2,100 = 50% × $4,200 upside".
