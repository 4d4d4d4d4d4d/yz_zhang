# Spec 16 — Customer Success: Health Scoring · Churn · SLA

Status: **Approved** · Review: R1 (2026-07-04) · Domain: `logic/customerSuccess.js`

## Problem

Spec 15's review put seven merged modules on a "presentation-dominant"
watchlist. A follow-up audit (spec 13 policy: *extract when the math
grows*) found that classification was **wrong for two of them**:
`CustomerHealth` carries a weighted health score, risk banding and a
churn-probability model; `SupportSLA` carries SLA-consumption and breach
logic. Both are untested domain algorithms living in components — exactly
what the logic layer exists to hold. This spec corrects the miscall and
extracts them.

## Design — `logic/customerSuccess.js`

### `scoreHealth(signals, weights = HEALTH_WEIGHTS)`
- Signals 0–100: `usage`, `payment`, `support`, `adoption`, `sentiment`.
- Weighted sum (default 0.30/0.15/0.15/0.25/0.15), rounded 0–100.
- Missing signals treated as 0; unknown keys ignored.

### `healthBand(score)` → `ok` ≥ 80 · `warn` ≥ 60 · `risk` else.

### `churnProbability(score, renewalInDays)`
- `base = max(0, 100 − score)/100` — unhealthy accounts churn.
- `urgency = max(0, (120 − renewalInDays)/120)` — near-renewal amplifies.
- `round((base·0.7 + urgency·0.3)·100)`, clamped 0–100.
- Renewal beyond the 120-day window contributes zero urgency (not
  negative — the `max(0, …)` guard is the reviewed fix; the inline code
  had it, the spec pins it).

### `slaStatus(ticket, now)`
Time is injected (spec 13 rule 2 — the inline module captured
`Date.now()` at load, making it untestable):
- `hoursLeft = (dueMs − now)/3.6e6`.
- `pctConsumed`: resolved → 100; else `min(100, (1 − hoursLeft/sla)·100)`
  — may be < 0 when far from the deadline (fresh ticket), by design; the
  UI clamps the bar width, the number stays truthful.
- `breach = hoursLeft < 0 && status !== 'resolved'`.

### `healthSummary(accounts)` / `slaSummary(tickets, now)`
Portfolio rollups (counts per band, MRR at risk, avg score; active/
breach counts, CSAT average over rated tickets) — pure reductions so the
dashboards share one source of truth.

## Guarantees
- Pure, total, deterministic given `now`.
- Score/churn bounded 0–100; band thresholds exact at 80/60.
- `slaStatus` never throws on a missing/naN due date (breach=false,
  hoursLeft=NaN surfaced, not crashed).

## Test plan
- scoreHealth: weighted fixture, missing-signal → 0, custom weights.
- healthBand boundaries at 80/60.
- churn: healthy+far → low; unhealthy+imminent → high; renewal>120 adds
  no urgency; bounds.
- slaStatus: breach when past due & unresolved; resolved → 100% consumed,
  no breach; injected `now` makes results deterministic.
- summaries: band counts, MRR at risk, CSAT average ignores nulls.

## Review record — R1
- ✅ Corrects the spec-15 watchlist miscall — audits are only as good as
  the follow-through; the policy worked because it was re-checked.
- ✅ `now` injection required for `slaStatus` (was load-time `Date.now()`).
- Verdict: **approved**.
