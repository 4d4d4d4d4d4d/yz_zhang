# Spec 36 — Cross-Timezone Meeting Planner

**Status:** Accepted · **Depends on:** 08 (immersive meeting), 20 (registry)

## 1. Problem (critical analysis)

The founding brief called for "跨国身临其境会议会谈" (cross-border immersive
meetings), and the Immersive Suite has a live meeting module — but there is
**no way to agree on a meeting time across time zones**, which is the very
first practical blocker for any cross-border call. Seller in Shanghai, buyer
in São Paulo: when do they both work? Every scheduling tool (Calendly, World
Time Buddy, Google Calendar's "find a time") solves working-hours overlap.
Its absence is a concrete, product-aligned gap.

## 2. Scope

- `logic/timezones.js` — pure, DST-correct overlap math:
  - `zoneOffsetMinutes(tz, now)` resolves a real IANA zone's offset via `Intl`.
  - `localHour(utcHour, offset)` and `overlapHours(offA, offB, window)` operate
    on plain offsets — deterministic and trivially testable, half-hour zones
    (IST +5:30) included.
  - `suggestSlot(hours)` picks the humane middle of the overlap window.
- `components/MeetingPlanner.vue` — a new `immersive/planner` sub-tab: pick two
  zones from a curated set of business hubs; see the overlap count, a suggested
  slot rendered in *both* parties' local times, and a 24-hour strip that
  highlights the shared window. Accessible selects; graceful "no overlap" state.
- Registry gains `immersive.planner`; i18n adds the sub-tab label + a `planner.*`
  block across all four locales (parity-enforced).

## 3. Review record

**R1 — offsets, not zone strings, in the math.** `Intl` zone resolution varies
subtly by ICU build. The overlap functions take numeric offsets so the tests
are exact and environment-independent; only the thin `zoneOffsetMinutes`
wrapper touches `Intl`, tested against DST-free anchors (UTC = 0, Tokyo = +540).

**R2 — frozen `now`.** The plan is computed against a single instant captured at
mount, so the strip and suggested slot never shift mid-view.

**R3 — reuse vs the existing `meeting.js` overlap.** `meeting.js` had a coarse
integer-hour overlap used only for the live-meeting avatar demo. Rather than
overload it, this ships a dedicated, IANA/DST-aware module — the scheduling
concern is distinct from the in-call concern.

**R4 — humane slot.** The suggestion is the *middle* of the overlap, not the
earliest, so neither side is pushed to the edge of their working day.

## 4. Tests
`tests/timezones.test.js`: offset anchors (UTC, JST), local-hour shift and
midnight wrap, half-hour zones, overlap correctness + symmetry + custom windows
+ empty case, and `suggestSlot` mid-window selection. The sub-tab render is
covered by the mount-smoke sweep; i18n parity by `tests/i18n.test.js`.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: picking Shanghai ↔ New York shows a (small)
overlap with a suggested slot in both locals; Shanghai ↔ São Paulo shows the
no-overlap state.
