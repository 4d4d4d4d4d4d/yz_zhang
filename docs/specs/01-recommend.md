# Spec 01 — AI Recommendation Engine

Status: **Approved** · Review: R1 (2026-07-02) · Domain: `logic/recommend.js`

## Problem

Operators need ranked, **explainable** ad-concept recommendations per
target market. Black-box scores don't build trust with cross-border
clients; every rank must decompose into named factors.

## Design

### Inputs
- `candidates[]`: `{ id, name, market, format, signals }` where `signals`
  holds normalized 0–1 factors: `affinity` (audience fit), `freshness`
  (creative fatigue inverse), `performance` (historical CVR index),
  `brandFit`, `localization` (market-language/culture match).
- `weights`: per-factor weights (default profile ships with the engine);
  caller may override per market.

### Algorithm — `rankCandidates(candidates, opts)`
1. Validate: unknown signal keys rejected; missing signals default 0.
2. Score = Σ (weightᵢ × signalᵢ) / Σ weights → normalized 0–100.
3. **Diversity re-rank**: greedy MMR-style pass — after picking each item,
   apply penalty `λ` to remaining candidates sharing the same `format`,
   so one format cannot sweep the top-N. `λ` configurable, default 0.15.
4. Output per item: `{ id, score, rank, explanation[] }` where
   `explanation` lists each factor's weighted contribution, sorted desc —
   the UI renders these as "why this ranked #1" chips.

### Guarantees
- Deterministic: same inputs → same ranking (stable sort, id tiebreak).
- Total: never throws on empty input (returns `[]`).
- Score bounds: 0 ≤ score ≤ 100 for valid signals.

## Test plan
- Weight override changes order as expected.
- Diversity penalty demotes same-format runs; λ=0 reproduces pure score order.
- Explanation contributions sum ≈ raw score.
- Empty/missing-signal candidates handled without throw.

## Review record — R1
- ✅ MMR-lite chosen over category quota (simpler, tunable, testable).
- ✅ Explanation-sum invariant added to test plan (reviewer request).
- Verdict: **approved**.
