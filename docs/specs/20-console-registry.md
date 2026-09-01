# Spec 20 — Single-Source Console Registry

Status: **Approved** · Review: R1 (2026-07-04)
Artifacts: `src/console/registry.js`, `src/views/Console.vue`, `tests/i18n.test.js`

## Problem

Spec 14's shell-coverage guard checks that every console section and
sub-tab has i18n keys — but against a `CONSOLE_SECTIONS` fixture
**hand-mirrored** inside `tests/i18n.test.js`. The real registry lives in
`Console.vue`. The two are kept in sync by hand; the v9/v11 merges added
sections to both by hand. If a future change updates `Console.vue` but not
the test mirror, the guard passes **vacuously** — it only checks the
sections it already knows about. The guard has a blind spot equal to its
own fixture staleness.

## Design

### `src/console/registry.js` — structure only
Export `SECTIONS`: ordered `[{ key, icon, subs: [subKey, …] }]`. No
component imports, no i18n — pure structural data, so it is safe to
import from both the Vue layer and the test layer.

### `Console.vue` derives from the registry
`Console.vue` imports `SECTIONS` and a local `COMPONENTS` map
(`'section/sub' → Component`) — component wiring stays in the view (it
must, it imports `.vue` files), but the **structure** (keys, order, sub
list) comes from the single source. The rendered `sections` array is
built by zipping `SECTIONS` with `COMPONENTS`; a registry sub with no
component throws at construction (fail-fast, caught by smoke/build).

### `tests/i18n.test.js` consumes the registry
The hand-mirror is deleted; `CONSOLE_SECTIONS` is derived from the
imported `SECTIONS`. Adding a section now *automatically* requires its
i18n keys across all locales — the shell-coverage assertion runs against
the real registry, not a copy. Blind spot closed.

### Registry consistency test
A small structural test: section keys unique, sub keys unique within each
section, every section non-empty. Cheap invariants that keep the single
source well-formed.

## Test plan
- i18n shell-coverage now iterates the real `SECTIONS`; a section added
  without translations fails (verified by construction — no fixture to
  forget).
- registry: unique section keys, unique subs per section, no empty section.
- Console.vue builds without a missing-component throw (smoke).

## Review record — R1
- ✅ Structure/component split: registry holds keys, the view holds the
  `.vue` map — the registry stays importable by tests without pulling in
  the whole component tree.
- ✅ Kept `registry.js` out of `src/logic/**` (it is data, not an
  algorithm) so the coverage gate's scope stays honest.
- Verdict: **approved**.
