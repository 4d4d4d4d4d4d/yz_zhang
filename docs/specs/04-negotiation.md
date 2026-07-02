# Spec 04 — Commercial Negotiation (商业洽谈)

Status: **Approved** · Review: R1 (2026-07-02) · Domain: `logic/negotiation.js`

## Problem

Cross-border deals stall on price/terms gaps and non-obvious redlines.
The copilot needs a quantitative core: is there a zone of possible
agreement, what's a defensible anchor, and which terms in a proposal
violate our playbook.

## Design

### `zopa(buyer, seller)`
- `buyer: { max }`, `seller: { min }` (reservation prices).
- Returns `{ exists, low, high, width, midpoint }`;
  `exists = buyer.max ≥ seller.min`. Non-existent zone → width 0, nulls.

### `suggestAnchor(zone, side, aggressiveness = 0.7)`
- Seller anchors between midpoint and high:
  `high − (1 − a) × width / 2`; buyer mirrors at the low end
  (`low + (1 − a) × width / 2`). A seller never anchors below the
  midpoint. Aggressiveness clamped to [0, 1]. Null zone → null.

### `evaluateTerms(proposal, playbook)`
- `playbook.rules[]`: `{ term, op: 'max'|'min'|'oneOf'|'required', value,
  severity: 'block'|'warn' }`.
- Each proposal term checked; output
  `{ verdict: 'accept'|'counter'|'reject', findings[] }`:
  any `block` finding → `reject`; only `warn` findings → `counter`;
  clean → `accept`. Missing `required` term is a finding of its severity.
- Findings carry `suggestion` (the nearest compliant value) so the UI can
  one-click a counter-proposal.

## Guarantees
- Pure and total: malformed rules are skipped with a `skipped[]` note,
  never a throw mid-evaluation.
- Anchor always inside ZOPA; aggressiveness clamped to [0, 1].

## Test plan
- ZOPA exists/absent, width/midpoint math.
- Anchor at aggressiveness 0 / 1 / clamp beyond range.
- Terms: block→reject precedence over warns; oneOf & required paths;
  suggestion equals rule boundary.

## Review record — R1
- ✅ Verdict precedence (any block ⇒ reject) made explicit after review.
- ✅ `skipped[]` chosen over throwing on malformed playbook rows.
- Verdict: **approved**.
