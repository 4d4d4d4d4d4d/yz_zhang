# Spec 26 — Notification Center: Cross-Domain Alert Inbox

Status: **Approved** · Review: R1 (2026-07-06)
Domains: `logic/notifications.js` · `components/NotificationCenter.vue`

## Problem

Operationally urgent facts live scattered across seven console sections:
an SLA breach in trust/support, MRR at churn risk in trust/health, a
compliance block in trust/posture, metering overage in recommend/metering,
a stalled deal in showcase/pipeline. Industry-standard operator consoles
(Stripe, Linear, GitHub) aggregate these into one notification inbox with
unread state and deep links. Ours has no aggregation surface — the
operator finds a breach only by visiting the right sub-tab.

## Design — `logic/notifications.js`

### Alert derivation — `deriveAlerts(inputs)`
Pure mapping from **real domain outputs** (spec 19's composition pattern —
consume outputs, never import domains):

| Input (real engine output) | Condition | Severity | Deep link |
|---|---|---|---|
| `sla` (slaSummary) | `breached > 0` | critical | trust?sub=support |
| `health` (healthSummary) | `risk > 0` | warning | trust?sub=health |
| `compliance` (assessCampaign) | gate `block`→critical / `review`→warning | | trust?sub=posture |
| `invoice` (metering invoice) | `overage > 0` | warning | recommend?sub=metering |
| `readiness` (dealReadiness) | `!readyToSign` | info | showcase?sub=pipeline |

Each alert: `{ key, severity, msgKey, params, route }` — copy stays in
i18n (`notify.msg.*` with interpolation params); the engine emits keys,
never strings. Missing inputs produce no alert (total function).

### Inbox — `createInbox({ limit = 50 })`
- `push(alert, now)`: **dedupe by `key`** — a repeat updates `at` and
  increments `count` instead of duplicating (alert storms collapse).
- `markRead(key)` / `markAllRead()` / `unreadCount()`.
- `list({ unreadOnly })`: newest first, unread before read at equal time.
- Retention: beyond `limit`, evict oldest **read** items first; unread
  items are never silently dropped (review decision — losing an unread
  critical is worse than exceeding a soft cap).

## Design — `NotificationCenter.vue`
- Bell with unread badge in the console header; panel lists alerts with
  severity dot, localized message, relative context, and a deep link
  (router push to `route`, marks the alert read).
- Demo inputs come from the same fixtures the modules use, run through
  the **real engines** (slaSummary, healthSummary, assessCampaign,
  invoice, dealReadiness) — the bell shows the truth of the demo data,
  not hand-written alerts.
- `notify.*` copy ×4 locales; parity gate enforces.

## Test plan
- deriveAlerts: each row of the table from real engine outputs (breach →
  critical, block vs review severity, no-input → no alert, all-healthy →
  only the readiness info or nothing).
- Inbox: dedupe increments count and refreshes `at`; unread ordering;
  markRead/markAllRead; eviction skips unread; limit respected.
- Browser: badge count > 0, panel opens, clicking the SLA alert lands on
  trust?sub=support and decrements the badge; zh copy renders.

## Review record — R1
- ✅ Engine emits i18n keys + params, not strings — locale switching
  re-renders past alerts correctly and the parity gate owns the copy.
- ✅ Eviction never drops unread items (soft cap over silent loss).
- Verdict: **approved**.
