# Spec 42 — Data Subject Requests (statutory deadlines)

**Status:** Accepted · **Depends on:** 05 (risk/legal), 41 (consent)

## 1. Problem (critical analysis)

Spec 41 added the **consent** pillar of privacy compliance; the other GDPR
pillar — **Data Subject Requests** (access/erasure/portability, Art. 15–22) —
was only a label. The trust tab is literally named "Controls · DSR", yet the
queue was a **static mock**: hardcoded `due` ISO dates and an `hoursLeft`
counter. Because today is past those dates, every request showed "0h left" —
a live staleness bug — and there was no statutory-deadline logic at all.

## 2. Scope

- `logic/dsr.js` — pure: `REGIME_DAYS` (GDPR 30 / CCPA 45 / LGPD 15 / APPI 14 /
  PIPL 15), `regimeDays` (unknown → 30, strictest common default), `dueAt`,
  `createDSR` (deadline from regime + arrival, `now` injected per spec 13 R2),
  `dsrStatus` (open / due_soon ≤7d / overdue / resolved), `hoursRemaining`
  (clamped), `summarizeDSR` (tally by derived status).
- `ControlsRegister.vue` — the DSR queue now derives each deadline from the
  regime and an arrival offset relative to `now`, so it never goes stale;
  rows show regime, live status colour, overdue flag, and a summary
  (`N open · M overdue`).

## 3. Review record

**R1 — regime drives the deadline, not a date.** A hardcoded `due` rots the
moment the clock passes it. Storing arrival + regime and computing the
deadline from `REGIME_DAYS` keeps the queue correct forever and encodes the
actual statutory rule.

**R2 — injected `now`.** `createDSR(..., now = Date.now())` follows the
RNG/time-injection convention (spec 13 R2, enforced by `architecture.test.js`),
so status is deterministic in tests.

**R3 — fail to the strictest default.** An unknown regime maps to 30 days
(GDPR-equivalent) rather than silently granting a longer window.

## 4. Tests
`tests/dsr.test.js`: statutory windows + unknown fallback, due-date math,
status transitions (open/due_soon/overdue/resolved), `hoursRemaining` clamp,
`summarizeDSR` tally + non-array guard. Queue rendering covered by mount-smoke.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: the DSR queue shows a live overdue row and a
non-zero countdown (no stale "0h left").
