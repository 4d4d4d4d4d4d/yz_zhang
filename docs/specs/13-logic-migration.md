# Spec 13 — Inline-Algorithm Migration to the Logic Layer

Status: **Approved** · Review: R1 (2026-07-03) · First target: `logic/bandit.js`

## Problem

Spec 00 R1 deferred one item: console modules built in v2–v4 carry their
algorithms inline in components — correct-looking but untestable, and the
same math can't be reused server-side later. This spec sets the migration
policy and executes the first (and highest-value) migration: the
multi-armed bandit inside `BanditExplorer.vue`.

## Migration policy

1. One migration per spec revision; each names its target component and
   the extracted API before code moves.
2. The extracted module must be **pure and deterministic under an
   injected RNG** — randomness comes in as a parameter, never `Math.random`
   hardcoded (that's what made the inline versions untestable).
3. The component keeps its exact UI contract; after migration it holds
   only presentation state. Behavior parity verified by smoke test.
4. Tests land in the same commit as the extraction — a migration without
   tests is just moving code.

## Design — `logic/bandit.js`

### `createBandit(arms, { epsilon = 0.15, rng = Math.random })`
- `arms`: `[{ id, truth }]` (truth = latent CVR for simulation).
- State per arm: Beta(α, β) posterior, pulls, conversions, traffic share.
- `step()`: with prob ε explore uniformly, else Thompson-sample every arm
  (mean + noise·√variance approximation, clamped [0,1]) and pull the max.
  Reward drawn from the pulled arm's `truth` via the injected RNG.
  Updates posterior, cumulative reward/optimal, regret series.
- `snapshot()`: arms with shares (α-proportional, rounded to sum 100),
  totals, regret history (window-capped at 200), efficiency.
- `reset()`: back to uniform priors, counters zeroed.
- `setEpsilon(v)`: clamped to [0, 1].

### Guarantees
- Same seed → identical run (pull sequence, posteriors, regret).
- ε = 0 → pure Thompson; ε = 1 → uniform exploration.
- Shares always sum to 100 (largest-remainder rounding).
- Regret series is *realized* regret (oracle − actual), so it may dip when
  a conversion lands; it trends upward over a long run and its window cap
  keeps memory bounded. (R1 amendment: draft claimed pointwise
  non-decreasing — true only for expected regret.)

## Test plan
- Determinism: two bandits with the same seeded LCG produce identical
  snapshots after N steps.
- Convergence: with a seeded RNG and 2 000 steps, the best-truth arm
  holds the plurality of pulls and >50 % traffic share.
- Posterior bookkeeping: pulls = α+β−2 per arm; conversions = α−1.
- Shares sum to exactly 100 at every step; regret non-decreasing;
  window cap respected; ε clamp; reset restores initial state.

## Migration queue
- ~~`RenderStudio.vue` render-plan builder → `logic/render.js`~~ (R2, done)
- ~~`PartnerMatcher.vue` (marketing site) → reuse `logic/matching.js`~~ (R3, done)
- ~~`ForecastSim.vue` what-if model → `logic/forecast.js`~~ (R4, done)
- Queue empty — remaining console modules carry only presentation logic.

## Review record — R1
- ✅ RNG injection made a hard policy rule (rule 2) — the whole point of
  the migration is testability.
- ✅ Behavior parity via smoke test required (rule 3) so migrations can't
  quietly change module behavior.
- Verdict: **approved**.

## Revision R2 (2026-07-03) — `RenderStudio.vue` → `logic/render.js`
- API: `buildRenderPlan({ targets, formats }, catalog)` — pure cartesian
  market × format expansion with language lookup; empty selections → `[]`,
  unknown ids skipped with a `skipped[]` note (draft silently dropped
  them — rejected in review).
  `advanceProgress(progress, rng)` — one tick of simulated render progress
  (`+8 + rng()·14`, capped 100), RNG injected per rule 2.
- Component keeps its timing loop (pacing is presentation).
- Verdict: **approved**.

## Revision R3 (2026-07-03) — `PartnerMatcher.vue` reuses `logic/matching.js`
- **Reviewed behavior change**: the marketing-site matcher's ad-hoc
  penalty scoring is retired in favor of spec 03's engine — one scoring
  model everywhere, so a demo score on the site matches the console.
  Partner DB entries gain `stage`; their editorial `score` maps to the
  trust factor (`score/100`). UI layout, filters and top-5 contract
  unchanged; displayed numbers legitimately shift (recorded here per
  spec 12 policy: spec first, then tests, then code).
- Verdict: **approved**.

## Revision R4 (2026-07-03) — `ForecastSim.vue` → `logic/forecast.js`
- API: `saturatingRevenue(ch, budgetK)` = `k·sat·(1−e^{−b/sat})`;
  `marginalRoas(ch, budgetK)` = `k·e^{−b/sat}`;
  `project(channels, totalBudget)` — per-channel budget/revenue/marginal/
  ROAS + portfolio totals;
  `rebalanceAllocations(channels, id, val)` — slider move redistributes
  proportionally, result always sums to 100;
  `optimalAllocation(channels, totalBudget)` — λ-sweep water-fill
  equalizing marginal ROAS, returns integer percentages summing to 100.
- Fully deterministic (no RNG in this domain).
- Guarantees under test: revenue monotone & saturating (≤ k·sat),
  marginal strictly decreasing, rebalance conservation, optimizer never
  returns a worse portfolio than the uniform split.
- Verdict: **approved**.
