# Spec 55 — Make the Orphan Audit Permanent

**Status:** Accepted · **Depends on:** 22 (architecture conformance), 50, 51

## 1. Problem (critical analysis)

Specs 50 and 51 each found a logic module that was **fully built, fully tested,
and wired to nothing**:

- `recommend.js` — the platform's flagship "explainable ranked recommendations"
  engine, while the surface that sells explainability ranked by an unweighted
  mean of decorative scores.
- `marketing.js` — a cent-exact water-fill budget allocator and pacing model,
  while its intended screen showed a hardcoded "AI suggestion" object.

Both passed every gate the repo had. Coverage was 100% on functions, the
architecture test enforced import isolation and time/RNG injection, and the
build was green — because none of those guards ask the question that mattered:
**does anything actually use this?** A tested module that ships to no user is
indistinguishable, from CI's point of view, from one that does.

That audit was manual — a shell loop I ran by hand. Anything found by hand
comes back.

## 2. Scope

Extends `tests/architecture.test.js` with a per-module pair of checks:

- **`<module> is consumed by the app`** — some file under `src/` outside the
  logic layer references `logic/<module>`, or the module appears in
  `CONSUMER_EXEMPT` for a legitimate non-app consumer (build tooling).
- **`<module> is covered by a test file`** — some file under `tests/`
  references it.

The exemption is itself verified: the exempted path must exist *and* actually
contain the reference, so an allowlist entry cannot outlive the consumer it
names.

## 3. Review record

**R1 — two independent checks, not one.** Consumption and coverage fail
separately. The teeth-check confirms this: a synthetic orphan with neither
fires both assertions; adding a test file leaves the consumer assertion firing
alone. A single combined check could have let one condition mask the other.

**R2 — exemptions must be falsifiable.** `bundleBudget.js` is genuinely
consumed by `scripts/check-bundle.mjs`, outside `src/`. Rather than hardcode a
name to skip, the exemption names the consumer and the test verifies that file
exists and references the module — so the allowlist rots loudly instead of
silently.

**R3 — string matching is the right level here.** The check greps for
`logic/<name>`, not an AST import graph. It is deliberately coarse: it cannot
be defeated accidentally, needs no parser, and a module referenced only in a
comment is a wiring problem worth surfacing anyway.

## 4. Tests
The guard is itself the test — 2 assertions per logic module, 60 in total
today. **Teeth-verified in three configurations**, each restored afterwards:
a synthetic orphan with no consumer and no test fails both; the same orphan
with a test added fails only the consumer check; and an exemption pointed at a
missing file fails with "exemption points at a missing file".

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle`
within budget. 750 tests across 58 files, up from 658 — the increase is this
guard's per-module assertions.
