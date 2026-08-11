# Spec 49 — ZOPA Band Fix + Surplus Split

**Status:** Accepted · **Depends on:** 04 (negotiation core)

## 1. Problem (critical analysis)

The Deal Room tab is named "Playbook · **ZOPA** · redline", and
`logic/negotiation.js` has had a correct, tested `zopa()` since spec 04. But
`NegotiationPlaybook.vue` never imported it — it hand-rolled its own overlap:

```js
start: Math.max(yourReservation, theirTarget)   // 52
end:   Math.min(yourTarget * 1.1, theirReservation) // 48.4
```

Two defects: it mixes **targets** with **reservations** (a ZOPA is bounded by
walk-away points; targets are aspirations that sit *outside* the zone), and it
applies an unexplained `× 1.1`. The result is `start > end`, so the band's
`v-if` was permanently false — **the flagship visual of the ZOPA tab never
rendered at all.**

Related: the module's `suggestAnchor` is framed in *price* space (seller
favours the high end). On a **discount** axis the preferences invert, so
calling it directly would anchor each party toward the wrong edge.

## 2. Scope

Extends `logic/negotiation.js` (same domain, one implementation of the rule):

- `discountZopa(buyerMinDiscount, sellerMaxDiscount)` — zone from the two
  reservations, delegating to the existing `zopa()`.
- `surplusSplit(zone, settlement)` — value capture per side; on the discount
  axis a higher settlement favours the buyer. Settlements outside the zone are
  clamped (you cannot capture surplus that does not exist); zero-width zones
  return `null`.
- `discountAnchor(zone, side, aggressiveness)` — maps the price/discount axis
  inversion once, so callers can't get it backwards.

`NegotiationPlaybook.vue` now consumes these, drops the inline math, and gains
a settlement slider with a surplus-split bar and suggested opening anchors.

## 3. Review record

**R1 — reservations define the zone, targets never do.** The data was
relabelled so the ordering is coherent: seller target 38% → buyer walk-away
44% → seller walk-away 52% → buyer target 58%. Zone = [44, 52]; both targets
sit outside it on each side's favourable end, which is the textbook picture.

**R2 — the axis flip is a real hazard, so it lives in one place.** I initially
wrote a test asserting `suggestAnchor(zone,'seller')` anchors toward the
seller's favourable edge. It **passed** — but only because the assertion
matched the price framing, not the discount one. `discountAnchor` now performs
the inversion, and a test pins the two framings against each other explicitly.

**R3 — clamp, don't extrapolate.** A settlement outside the zone is clamped to
it rather than producing shares above 100% or below 0%.

## 4. Tests
`tests/zopa.test.js` (15), including a dedicated **REGRESSION** case asserting
the shipped numbers yield a positive-width, renderable zone; zone bounds and
midpoint; no-zone and degenerate (zero-width) cases; equivalence with `zopa()`;
surplus split at both edges and the midpoint, shares always summing to 1,
out-of-zone clamping, null guards; and axis-aware anchoring including the
explicit price-vs-discount inversion.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget, plus a browser smoke: the band renders at left 40% / width
22.86% (zone 44–52 on a 30–65 scale), the midpoint splits 50/50, the low edge
gives the seller 100%, and anchors land at 45.2% / 50.8%.
