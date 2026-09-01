# Spec 03 — Business Matchmaking (业务对接)

Status: **Approved** · Review: R1 (2026-07-02) · Domain: `logic/matching.js`

## Problem

Going overseas means finding the right local partner — distributor,
agency, MCN, platform rep. Matching must weigh category fit, market
overlap, stage compatibility and verified trust, and must say **why** a
partner fits, because the fit story is the opener of the business
conversation.

## Design

### `scorePartner(need, partner)`
Factors (0–1 each), combined with fixed weights (sum = 1):
- `category` (0.30): Jaccard overlap of category tags.
- `market` (0.30): overlap of target markets vs partner's active markets;
  exact-market presence scores 1, adjacent-region scores 0.5.
- `stage` (0.15): distance on ordered ladder seed → growth → scale →
  enterprise (adjacent = 0.5, same = 1, else 0).
- `trust` (0.25): partner's verification score (0–1) from the trust layer
  (KYB done, references, showcase-verified track record).

Output `{ score (0–100), tier, reasons[] }`:
- `tier`: `strong` ≥ 75, `good` ≥ 55, `explore` ≥ 35, else `weak`.
- `reasons`: top factors with human-readable framing for the opener.

### `rankPartners(need, partners, { topN })`
Stable ranked list; filters `weak` unless `includeWeak`.

## Guarantees
- Symmetric-safe: missing arrays treated as empty, never throw.
- Verified-partner priority: equal raw fit → higher trust wins the tie.

## Test plan
- Perfect match → 100 / strong; disjoint → weak.
- Adjacent market/stage produce the specified partial credit.
- Tie broken by trust; tier boundaries exact at 75/55/35.

## Review record — R1
- ✅ Trust weight raised 0.15 → 0.25 (aligns with 增加互信 goal).
- ✅ Reasons framed as conversation openers, not raw numbers.
- Verdict: **approved**.
