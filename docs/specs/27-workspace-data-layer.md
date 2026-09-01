# Spec 27 — Workspace Data Layer (batch): Single Fixture Source · Persistent Store · Error Boundary

Status: **Approved** · Review: R1 (2026-07-07)
Artifacts: `src/data/workspace.js` · `src/store/workspace.js` ·
`components/ModuleBoundary.vue` (+ rewired consumers)

## Problem (from the v22 critical review)

Three structural weaknesses, batched because they share one root — the
app has pure logic engines but **no data layer** between them and the
components:

1. **Fragmented demo data.** "Lumen Studios" and friends are declared
   independently in CustomerHealth, SupportSLA, UsageMetering and
   NotificationCenter with mutually inconsistent numbers. The bell can
   claim two SLA breaches while the support view shows a different set.
2. **No persistence.** Notification read-state and currency preference
   reset on every reload; the i18n locale is the only persisted pref.
3. **Snapshot notifications.** The inbox is computed once at component
   mount, private to that component instance.

Plus one adjacent robustness gap: **no error boundary** — any of the 44
module components throwing during render blanks the whole console.

## Design

### 1 · `src/data/workspace.js` — one source of demo truth
Exports the shared entities: `ACCOUNTS` (health signals, MRR, renewal),
`ticketsAt(now)` (SLA tickets materialized from hour-offsets so time
stays injectable), `TENANTS` + `METERS` (usage/billing), `CAMPAIGN`
(compliance attributes), `DEAL` (readiness inputs). Data only — no
logic, no imports of engines (mirror of the registry pattern, spec 20).
Modules that consume these entities import them instead of redeclaring.
(Narrative-only fixtures — e.g. UpsellEngine's play/email copy — stay
local by design; they are content, not shared entities. Noted, not
hidden.)

### 2 · `src/store/workspace.js` — reactive store with localStorage
- `prefs`: currency override + notification read-keys, synced to
  `adforge.prefs`; malformed storage falls back to defaults (never
  throws at import time).
- `useInbox()`: singleton inbox built by running the **real engines**
  (slaSummary/healthSummary/assessCampaign/invoice/dealReadiness) over
  the workspace data, applying persisted read-state; `markRead`/
  `markAllRead` persist; `unread` is reactive and shared across all
  consumers.

### 3 · Rewiring
CustomerHealth ← `ACCOUNTS`; SupportSLA ← `ticketsAt`; UsageMetering ←
`TENANTS`/`METERS`; NotificationCenter ← `useInbox()`; Pricing ←
persisted currency pref. The bell and the pages now show the same facts,
and read-state survives reload.

### 4 · `ModuleBoundary.vue`
Wraps the active console module; `onErrorCaptured` renders a localized
fallback card (module name + retry) instead of blanking the console.
Boundary copy `boundary.*` ×4 locales.

## Test plan
- workspace: structural invariants (unique account/tenant names, every
  tenant has meters, ticket offsets materialize against an injected now).
- store: read-state persists across a simulated reload (fresh import
  state + localStorage), malformed storage falls back, markAllRead
  persists; inbox derives from workspace data via real engines (counts
  match the fixture's truth).
- boundary: a child that throws during render yields the fallback card,
  not an empty tree; a healthy child renders untouched.
- Browser: bell count matches support view's breach count (single
  truth); mark-read survives a reload; currency override survives a
  reload; a forced module error shows the fallback card.

## Review record — R1
- ✅ Batched 1–3 because splitting them would rewire the same components
  twice; the error boundary rides along as it touches the same shell.
- ✅ Store kept dependency-free (Vue `reactive` + localStorage, no pinia)
  — one new concept, zero new deps.
- ✅ Data module carries no logic and no engine imports — it is to
  fixtures what the registry (spec 20) is to structure.
- Verdict: **approved**.
