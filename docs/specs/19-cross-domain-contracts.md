# Spec 19 — Cross-Domain Contract Tests (pipeline integration)

Status: **Approved** · Review: R1 (2026-07-04) · Test: `tests/integration.pipeline.test.js`

## Problem

Spec 11's trust pipeline composes the outputs of five domains — showcase,
field verification, compliance, due diligence, negotiation. But every
test in the suite is a **unit** test: each domain is tested alone, and
`pipeline.test.js` feeds `dealReadiness` hand-written fixtures like
`{ score: 80 }`. Nothing verifies that the **real** domain functions
produce outputs shaped the way the pipeline reads them.

Concretely, the pipeline reads `reel.score`, `fieldCase.state`,
`fieldCase.chainValid`, `compliance.gate`, `diligence.gate`,
`terms.verdict`. The real producers are `trustScore()` (→ `score`),
`assessCampaign()`/`dueDiligence()` (→ `gate`), `evaluateTerms()`
(→ `verdict`), and — critically — `verifyChain()` returns `{ valid }`,
which `TrustPipeline.vue` **adapts** to `chainValid`. That adapter, and
all these field contracts, are untested: a rename in any domain output
keeps every unit test green while silently breaking deal readiness.

This is a gap unit tests structurally cannot close. Integration tests can.

## Design — `tests/integration.pipeline.test.js`

Drive `dealReadiness` with **only real domain outputs**, no synthetic
shapes:

1. **All-green, end to end.** Build the scenario from the actual APIs:
   - reels via `trustScore({ provenance, metricsVerified, clientAttested,
     complianceGate })`;
   - a field case walked through the real `createCase → advanceCase(...)`
     state machine with `addEvidence`, then `verifyChain(k).valid`
     adapted to `chainValid` (the canonical wiring, asserted here);
   - `assessCampaign` / `dueDiligence` with all requirements met;
   - `evaluateTerms` on a clean proposal.
   → expect `score 100`, `stage 'ready'`, `readyToSign true`.

2. **Real hard-fails.** Produce the block from the real engines, not a
   literal:
   - `dueDiligence` with `sanctions` unchecked → real `gate: 'block'`
     → pipeline `hardFail`, score ≤ 40;
   - a field case whose evidence is tampered after sealing, run through
     the real `verifyChain` → `valid: false` → `chainValid: false`
     → `hardFail`.

3. **Field-contract assertions.** Assert the producers actually emit the
   keys the pipeline consumes: `trustScore` has `score`; `assessCampaign`
   /`dueDiligence` have `gate ∈ {pass,review,block}`; `evaluateTerms` has
   `verdict ∈ {accept,counter,reject}`; `verifyChain` has `valid`. These
   fail loudly on a rename — the early-warning the pipeline lacks.

## Test plan
- All-green real scenario → 100 / ready / readyToSign.
- Real sanctions block and real tampered chain → hardFail, score ≤ 40.
- Contract assertions on every consumed field.
- The `verifyChain().valid → chainValid` adapter reproduced and asserted
  so a future refactor of the component wiring has a test to answer to.

## Review record — R1
- ✅ Integration test uses real outputs exclusively — a fixture here would
  reintroduce the exact blind spot it exists to cover.
- ✅ The component adapter (`.valid → chainValid`) is pinned in the test,
  since it is real production wiring that lives outside the logic layer.
- Verdict: **approved**.
