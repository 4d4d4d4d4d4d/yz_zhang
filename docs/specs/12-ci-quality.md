# Spec 12 — CI & Test Maintenance (持续迭代基建)

Status: **Approved** · Review: R1 (2026-07-03) · Artifact: `.github/workflows/ci.yml`

## Problem

Specs 01–11 established "tests must pass before merge" as a quality gate,
but enforcement was manual. Continuous iteration needs the gate wired
into the repository itself.

## Design

### CI workflow
GitHub Actions, on `push` and `pull_request`:
1. Node 22 with npm cache (keyed on `app/package-lock.json`).
2. `npm ci` in `app/` (lockfile-exact, no drift).
3. `npm test` — the full Vitest suite; any failure fails the run.
4. `npm run build` — the production build must stay green.

Single job; matrix/browser jobs deferred until there is more than one
runtime target.

### Test-maintenance policy
- Every `logic/` module ships with a test file mirroring its spec's
  "Test plan" section — the spec is the source of the assertions.
- A behavior change starts with a spec edit (design + review record),
  then the test, then the code.
- Tests may not be deleted to make CI pass; a failing test is either a
  regression (fix the code) or a spec change (amend the spec first).

## Review record — R1
- ✅ `npm ci` over `npm install` (reproducible, catches lockfile drift).
- ✅ Build step kept in CI: type-less JS means the build is the only
  whole-app static check we have.
- Verdict: **approved**.
