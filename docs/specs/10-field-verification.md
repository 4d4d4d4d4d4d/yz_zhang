# Spec 10 — Field Verification Network (线下专员 · 跨国实地调查)

Status: **Approved** · Review: R1 (2026-07-02) · Domain: `logic/fieldVerify.js`

## Problem

Digital trust has a ceiling: at some deal size, someone has to physically
walk the factory, sight the licenses, meet the team. AdForge keeps
vetted local specialists in key markets; a buyer orders an investigation,
a specialist executes on-site, and every piece of evidence lands in a
tamper-evident chain that feeds the showcase trust score (spec 06).

## Design

### Specialist matching — `matchSpecialists(request, specialists)`
- Request: `{ country, languages[], expertise[], urgencyDays }`.
- Hard filter: specialist must cover the country (resident or licensed
  cross-border list) — no remote-only assignment for on-site work.
- Score (0–100): language overlap 0.30, expertise overlap 0.40,
  availability 0.30 (`availableInDays ≤ urgencyDays` full credit, ≤ 2×
  half credit, else 0). Ranked; ties break toward higher rating then id.

### Case workflow — `createCase(...)`, `advanceCase(case, event)`
Linear state machine, no skips, no regressions:
`requested → assigned → on-site → evidence-collected → report-drafted → attested → closed`
- Illegal transition → `{ ok: false, reason }` (case unchanged).
- `attested` requires `case.evidence.length > 0` **and** a verified
  chain — an attestation over zero evidence is refused by construction.
- Every accepted transition appends `{ at, from, to }` to an audit log.

### Evidence chain — `addEvidence(case, item, now)` / `verifyChain(case)`
- Each item hashed (djb2-style demo hash) over
  `prevHash + type + ref + timestamp` — hash-chained like a mini ledger.
- `verifyChain` recomputes; any mutation of an earlier item breaks every
  later link → `{ valid: false, brokenAt }`.

## Test plan
- Matching: country hard-filter, weight math, urgency credit tiers,
  deterministic tiebreak.
- Workflow: full happy path; skip and regression rejected; attest with
  empty evidence rejected; audit log grows only on accepted transitions.
- Chain: valid after N adds; tampering item k → brokenAt = k; empty
  chain valid.

## Review record — R1
- ✅ Country coverage is a hard filter, not a scored factor (an on-site
  job cannot be "80% in the right country").
- ✅ Attestation gated on non-empty verified chain (paper-only attests
  rejected in review).
- Verdict: **approved**.
