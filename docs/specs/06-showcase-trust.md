# Spec 06 — Digital Video Showcase & Trust Links (数字视频展示 · 互信)

Status: **Approved** · Review: R1 (2026-07-02) · Domain: `logic/showcase.js`
New console section: **Showcase** (gallery / trust links / verification queue)

## Problem

Closing cross-border deals needs proof, not promises. Prospects abroad
can't visit the office; they need a verifiable digital showcase — real
rendered video work, provenance-signed, with metrics a third party can
trust — shareable under control. This is the trust surface that converts
matchmaking (spec 03) into signed deals (spec 04).

## Design

### 1. Showcase reels & trust score — `trustScore(reel)`
A reel carries verification evidence: `provenance` (C2PA credential
present & chain intact), `metricsVerified` (platform-API-sourced numbers),
`clientAttested` (counterparty signed the case study), `complianceGate`
(spec 05 gate === pass). Score 0–100 with weights 35/25/20/20; badge tier:
`verified` ≥ 85, `substantiated` ≥ 60, `claimed` otherwise. UI shows the
badge and the evidence breakdown — the "why should I trust this" panel.

### 2. Trust Links — `createTrustLink(opts)` / `validateTrustLink(link, now)`
Scoped, expiring share links for a curated reel set:
- `scopes ⊆ {assets, metrics, provenance, pricing}` — least privilege;
  `pricing` never included by default.
- `expiresInDays` (default 7, max 90 — clamped), `watermark` default ON;
  turning watermark off requires `scopes` to exclude `assets` (review
  decision R1: raw unwatermarked assets never leave via link).
- Token: 24-char unguessable id from injectable RNG (testable), carries
  no payload — server-side lookup model.
- `validateTrustLink` → `{ valid, reason?: 'expired'|'revoked'|'malformed' }`.
- `revokeTrustLink(link)` idempotent.

### 3. Verification queue — `createQueue(limit)`
Bounded-concurrency scheduler used by the verification pipeline UI
(provenance hash check → metrics pull → compliance gate):
- `enqueue(task, { priority = 1 })` → Promise of task result.
- At most `limit` tasks in flight; higher priority first, FIFO within a
  class; failures release the slot and reject only that caller.
- Introspection: `{ inFlight, queued, done, failed }` for the saturation UI.

## Test plan
- trustScore weights/tiers; all-evidence → 100/verified.
- Link: scope clamp, expiry clamp, watermark rule enforced, validate on
  expired/revoked/malformed, token uniqueness across 1k generations.
- Queue: never exceeds limit under burst; priority ordering; FIFO within
  class; failed task frees slot; counters accurate on completion.

## Review record — R1
- ✅ Watermark-off requires no-assets scope (asset-leak scenario raised).
- ✅ Token is opaque id, not encoded payload (client-decode risk rejected).
- ✅ Queue is the shared concurrency primitive for the platform story (spec 00 §3).
- Verdict: **approved**.
