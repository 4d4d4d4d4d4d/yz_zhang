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

## Migration queue (future revisions)
- `RenderStudio.vue` render-plan builder → `logic/render.js`
- `PartnerMatcher.vue` (marketing site) → reuse `logic/matching.js`
- `ForecastSim.vue` what-if model → `logic/forecast.js`

## Review record — R1
- ✅ RNG injection made a hard policy rule (rule 2) — the whole point of
  the migration is testability.
- ✅ Behavior parity via smoke test required (rule 3) so migrations can't
  quietly change module behavior.
- Verdict: **approved**.
