# AdForge Commercialization Platform — Architecture Spec

Status: **Approved** · Review: R1 (2026-07-02) · Owner: platform

## 1. Goal

Ship a go-global commercial platform around AI ad rendering: a marketing
site that converts, and an operator console that runs the business —
recommendations, marketing, partner matchmaking, negotiation, risk & legal,
and a **digital video showcase** layer that builds cross-border trust and
closes deals.

## 2. Module map (分模块设计)

Each capability domain is an isolated module with three layers:

| Layer | Location | Rule |
|---|---|---|
| Domain logic | `app/src/logic/<domain>.js` | Pure functions / classes. No Vue, no DOM, no network. Deterministic given inputs (RNG injectable). Unit-tested. |
| UI modules | `app/src/components/*.vue` | One component per sub-module. Imports logic layer; owns only presentation state. |
| Shell | `app/src/views/Console.vue` | Declarative section registry (`sections[]`). Adding a module = one registry entry, no cross-module edits. |

Domains: `recommend`, `marketing`, `matching`, `negotiation`, `riskLegal`,
`showcase`. Cross-domain imports between logic modules are forbidden;
shared helpers live in `logic/core.js` only.

## 3. Concurrency (并发性)

The product story is a render/verification pipeline that must feel like a
real delivery platform under load:

- **Bounded concurrency**: work is scheduled through a semaphore-style
  queue (`logic/showcase.js → createQueue(limit)`), never unbounded
  `Promise.all`. Mirrors the production render farm's worker-pool model.
- **Priority + fairness**: queue orders by priority then FIFO arrival;
  starvation is impossible because priority classes are finite and
  arrival order breaks ties.
- **Back-pressure**: queue exposes depth + in-flight counts so UI can
  show saturation instead of silently buffering.
- **Cancellation-safe**: tasks resolve/reject exactly once; a failed task
  releases its slot (no leaked permits).

## 4. Security (安全性)

- **Least-privilege sharing**: showcase Trust Links are scoped
  (assets, metrics, provenance), watermarked by default, and expire.
  Link tokens are unguessable and never encode payload data client-side.
- **Provenance**: every showcased render carries C2PA-style content
  credentials (issuer, capture chain, hash) surfaced in the UI.
- **Compliance gates**: risk/legal rule engine blocks publish/share on
  hard violations (see spec 05); UI renders the gate, logic decides it.
- **No secrets in repo**: demo data only; all tokens are generated mocks.

## 5. Quality gates

1. Spec per domain (this directory), reviewed before code.
2. Logic layer covered by Vitest unit tests (`app/tests/`).
3. `npm run test` and `npm run build` must pass before merge.

## Review record — R1

- ✅ Registry-driven shell confirmed extensible (5 → 6 sections, single entry).
- ✅ Queue design reviewed against starvation & permit-leak scenarios; both covered by required tests.
- ⚠️ Deferred: moving existing v2–v4 component-inline algorithms onto the
  logic layer is incremental; new modules must use the logic layer from day one.
- Verdict: **approved to build**.
