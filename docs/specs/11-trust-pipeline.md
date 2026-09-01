# Spec 11 — Trust Pipeline: Evidence → Showcase → Compliance → Signature

Status: **Approved** · Review: R1 (2026-07-03) · Domain: `logic/pipeline.js`

## Problem

Specs 01–10 each built one capability. A deal doesn't close on any one of
them — it closes when the chain holds end to end: verified showcase
evidence, an attested field investigation, a passing compliance gate,
and commercially acceptable terms. Operators need one **deal-readiness**
view that says how far a deal is from signature and exactly what is
blocking it.

## Design

### Composition, not coupling
`pipeline.js` never imports other domain modules (spec 00 §2 rule
preserved). It consumes their **outputs**:

```
dealReadiness({
  reels:        [{ score, badge }],          // showcase.trustScore results
  fieldCase:    { state, chainValid },       // fieldVerify case + verifyChain
  compliance:   { gate },                    // riskLegal.assessCampaign
  diligence:    { gate },                    // riskLegal.dueDiligence
  terms:        { verdict }                  // negotiation.evaluateTerms
})
```

### Stages & scoring
Four gates, 25 points each, evaluated in order:

| Stage | Full credit | Half credit | Zero |
|---|---|---|---|
| `evidence` | ≥1 reel and avg reel score ≥ 60 | ≥1 reel, avg < 60 | no reels |
| `verification` | case `attested`/`closed` with `chainValid` | case ≥ `evidence-collected` | earlier / broken chain |
| `compliance` | both gates `pass` | worst gate `review` | any gate `block` |
| `commercial` | verdict `accept` | `counter` | `reject` / missing |

- `score` = sum (0–100).
- `stage` = first gate below full credit; all full → `ready`.
- `readyToSign` = all four at full credit.
- `blockers[]`: one entry per non-full gate with a human `action`
  ("collect a second verified reel", "re-run sanctions screening", …).
- **Hard-fail override**: any `block` compliance gate or broken evidence
  chain caps `score` at 40 and forces `readyToSign: false` regardless of
  other gates — you cannot out-market a sanctions hit (review decision).

### Guarantees
- Pure, total: missing inputs are treated as zero-credit, never a throw.
- Monotonic per gate: improving one input never lowers the score
  (hard-fail override excepted, and it only ever lowers).
- Deterministic; blockers ordered by stage order.

## Test plan
- All-green fixture → 100 / `ready` / `readyToSign` / no blockers.
- Each gate independently at half and zero, stage points at first gap.
- Hard-fail: compliance `block` caps at 40 even with 3 full gates;
  broken chain likewise.
- Empty input → score 0, stage `evidence`, 4 blockers, no throw.

## Review record — R1
- ✅ Consume domain outputs instead of importing domain modules —
  keeps the spec 00 no-cross-import rule intact.
- ✅ Hard-fail cap added: a formally "75-point" deal with a sanctions
  block must not look three-quarters done.
- Verdict: **approved**.
