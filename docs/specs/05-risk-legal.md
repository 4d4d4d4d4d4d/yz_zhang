# Spec 05 — Risk & Legal Compliance Engine

Status: **Approved** · Review: R1 (2026-07-02) · Domain: `logic/riskLegal.js`

## Problem

Every market a campaign ships to carries its own regime (GDPR, CCPA,
APPI, PIPL, DSA…) and content rules. Publish/share actions must pass a
deterministic gate; "we'll check later" is how fines happen.

## Design

### Rule registry
`MARKET_REGIMES`: market → regimes; `REGIME_REQUIREMENTS`: regime →
requirement keys (e.g. `consent`, `dpa`, `localization`, `ageGate`,
`adDisclosure`, `provenance`).

### `assessCampaign(campaign)`
- `campaign: { markets[], attributes: {key: bool} }` where attributes
  assert satisfied requirements (e.g. `consent: true`).
- Union all requirements from all target markets' regimes; each unmet
  requirement becomes a finding with severity from a fixed table
  (`consent`, `dpa` → `block`; others → `warn`).
- Output `{ riskScore 0–100, gate: 'pass'|'review'|'block', findings[] }`
  - score = weighted unmet severity (block 25, warn 10, capped 100);
  - gate: any block → `block`; any warn → `review`; clean → `pass`.

### `dueDiligence(partner)`
- Checklist scoring for counterparty risk: `kyb`, `sanctions`,
  `references`, `financials`, `dataProcessing`. Missing `sanctions` or
  `kyb` → gate `block`. Returns same shape as above so UI shares one
  renderer.

## Guarantees
- Unknown market → explicit `unknown-market` warn finding (never silently
  passes).
- Deduplicated: shared requirements across regimes counted once.
- Deterministic and pure.

## Test plan
- Multi-market union & dedupe; unknown market warns.
- Gate precedence block > review > pass; score cap at 100.
- Due diligence: missing sanctions blocks even if all else present.

## Review record — R1
- ✅ Fail-closed on unknown markets (was fail-open in draft — rejected).
- ✅ One output shape across campaign & partner checks for UI reuse.
- Verdict: **approved**.
