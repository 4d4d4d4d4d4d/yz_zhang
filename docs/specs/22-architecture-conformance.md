# Spec 22 — Architecture Conformance Tests

Status: **Approved** · Review: R1 (2026-07-05) · Test: `tests/architecture.test.js`

## Problem

Two load-bearing architecture rules exist only as prose:

1. **Spec 00 §2** — logic modules are pure and isolated: no Vue, no DOM,
   no network, no cross-domain imports (shared helpers via `logic/core.js`
   only).
2. **Spec 13 rule 2** — randomness and time are injected, never hardcoded:
   `Math.random` / `Date.now` may appear **only as default parameter
   values** (`rng = Math.random`, `now = Date.now()`), so every algorithm
   stays deterministic under test.

Both have been honored across 20 modules — by discipline alone. A single
`import { trustScore } from './showcase.js'` inside another domain, or a
bare `Math.random()` in a function body, would land silently: it breaks
no unit test, no coverage threshold, no mount smoke. The same applies to
the specs index: its table maps spec → module → test file by hand, and a
rename leaves dead references without any check failing.

Audit before this spec: current tree is fully compliant (zero imports in
`src/logic`, all RNG/time occurrences in default-parameter position) —
the rules are true today; this spec keeps them true.

## Design — `tests/architecture.test.js`

Static source checks over `src/logic/*.js` (read via `fs`, no execution):

### Isolation (spec 00 §2)
Any `import`/`require` in a logic module fails the test unless it targets
`./core.js` (the one sanctioned shared-helper location). This forbids
cross-domain imports, `vue*`, node builtins and network clients in one
stroke — the logic layer stays a dependency-free island.

### Injection (spec 13 rule 2)
Strip occurrences of the sanctioned default-parameter forms, then any
**remaining** `Math.random` or `Date.now` token fails with file and line.
Sanctioned forms (R1 correction — the first draft stripped any
`= Math.random`, which also exempted the body call
`const jitter = Math.random()`; the teeth test caught the evasion):
- `= Math.random` **not followed by `(`** — passing the function
  reference as a default parameter; a body call always has parens.
- `now = Date.now()` — an injected time parameter, by convention named
  `now`. (Known lexical limit: a body-scoped `const now = Date.now()`
  would evade; accepted and documented — revisit with AST parsing if it
  ever bites.)

### Docs consistency
Every markdown link target in `docs/specs/README.md` resolves to an
existing spec file, and every backticked `logic/*.js` / `tests/*.js`
path in the index table exists on disk. Renames can no longer leave the
index lying.

## Test plan
- Current tree passes all three checks.
- Teeth (verified during development): a synthetic cross-domain import
  and a bare `Math.random()` in a body each fail with the offending
  file named; a bogus index reference fails docs consistency.

## Review record — R1
- ✅ Static text checks over AST parsing: the rules are lexical
  (import lines, token position); a parser adds weight without adding
  discrimination here. Revisit if false positives ever appear.
- ✅ `./core.js` allowance kept even though the file doesn't exist yet —
  the test encodes spec 00's rule as written, not today's stricter
  accident.
- Verdict: **approved**.
