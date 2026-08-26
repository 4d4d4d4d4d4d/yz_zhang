# Spec 54 — Partner Match Score Derived From Its Own Breakdown

**Status:** Accepted · **Depends on:** 03 (matching core)

## 1. Problem (critical analysis)

`BusinessMatchHub` showed each partner a headline score (94, 91, 88, 90) *and*,
directly beneath it, a "Fit breakdown" of the four dimensions that supposedly
produce it. Both were hardcoded independently — and they disagree:

| partner | asserted | weighted from its own bars | delta |
|---|---|---|---|
| Lumen | 94 | 93.1 | +0.9 |
| Aurora | 91 | 91.6 | −0.6 |
| Northwave | 88 | 87.5 | +0.5 |
| **Cobalt** | **90** | **87.3** | **+2.7** |

This is not merely cosmetic. Cobalt is over-credited by 2.7 points, which
**flips the ranking**: the screen presented Cobalt above Northwave, while the
evidence it displayed said the opposite. On a partner-selection surface, the
ordering *is* the product.

`logic/matching.js` already defined weights over these same dimensions and was
consumed only by `PartnerMatcher.vue`.

## 2. Scope

- `logic/matching.js` — adds `DIRECTORY_WEIGHTS` and `compositeFit(fit, weights)`
  returning the weighted score plus per-dimension contributions, sorted by
  contribution. Values are clamped to 0..100; unknown dimensions are ignored.
- `BusinessMatchHub.vue` — the score is now the composite of the bars; the
  network list is **sorted by it**; the breakdown shows each dimension's weight
  and the points it contributes; the dead asserted `score:` fields were deleted
  from the data so nothing suggests they are authoritative.

## 3. Review record

**R1 — a missing dimension renormalises rather than scoring zero.** Spec 53
deliberately treats an absent buying signal as evidence against expansion. The
opposite call is right here: an unmeasured fit dimension is missing
*information*, not a zero fit, so the remaining weights renormalise. The two
specs differ because absence means different things in the two domains, and
that is stated in the code rather than left as an inconsistency.

**R2 — the directory keeps its own weights.** The needs-matcher scores
`category/market/stage/trust`; the directory scores `delivery speed` instead of
`stage`, because deal stage is meaningless for a standing agency listing. Both
share one implementation of the weighted-composite rule rather than one weight
table forced onto two different questions.

**R3 — delete the superseded data.** The asserted `score:` values were being
silently overridden by the computed one. Leaving them in the source would have
left a plausible-looking number for the next reader to trust.

## 4. Tests
`tests/compositeFit.test.js` (10): the weighted average against a hand-computed
value, contributions summing to the score and ordered largest-first, weights
totalling 1, unknown dimensions ignored, renormalisation when a dimension is
absent (and specifically *not* treating it as zero), clamping, and empty/unusable
input. A dedicated **REGRESSION** block pins the corrected ordering —
Northwave 87.5 above Cobalt 87.3 — and that the already-consistent top two are
preserved.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget, plus a browser smoke: the list ranks Lumen 93.1 → Aurora 91.6 →
Northwave 87.5 → Cobalt 87.3, and Lumen's bars read 28.8 + 27.6 + 23.5 + 13.2,
summing exactly to the 93.1 headline.
