# Spec 37 — Add-to-Calendar (.ics) & Adjustable Working Hours

**Status:** Accepted · **Depends on:** 36 (meeting planner)

## 1. Problem (critical analysis)

Spec 36 finds a meeting slot but the operator **can't do anything with it** —
no way to put it on a calendar, so the journey dead-ends. Every scheduler
(Calendly, Google "find a time") ends in an `.ics` / "add to calendar" action.
Separately, the planner's working hours were **hardcoded 9–18** for both
sides, which makes the overlap a toy — real cross-border partners keep
different hours, and the whole point is to model that.

## 2. Scope

- `logic/ics.js` — pure **RFC 5545** VEVENT builder: UTC `DTSTART/DTEND/DTSTAMP`,
  TEXT escaping (`\` `;` `,` newline), 75-char line folding, CRLF joins, optional
  `DESCRIPTION`/`LOCATION`. Deterministic given an injected `now`/`uid`.
- `MeetingPlanner.vue`:
  - **Adjustable hours** — each party picks a shift preset (early 07–16 /
    standard 09–18 / late 11–20); the overlap recomputes live.
  - **Add to calendar** — when a slot exists, download a 1-hour `.ics` for it
    (today at the slot's UTC hour) via the Blob pattern from spec 35.
- i18n: `planner.add`, `planner.hours`, `planner.shift.*` across all four
  locales; the now-inaccurate "09:00–18:00" copy in `planner.working` is
  replaced with a hours-agnostic legend.

## 3. Review record

**R1 — reuse the download + injection patterns.** The Blob/anchor download is
the same mechanism spec 35 uses for CSV; `now`/`uid` are injected so the ICS is
byte-stable in tests, mirroring the RNG/time-injection rule (spec 13 R2).

**R2 — char-based folding.** True RFC folding counts octets; the builder folds
by character (octet-exact for ASCII, close enough for the CJK content real
clients accept). Documented, not hidden.

**R3 — shift presets over free hour inputs.** Three presets communicate the
cross-border-hours idea in one click without four numeric inputs cluttering the
panel; the overlap engine already takes arbitrary windows, so richer inputs can
follow without touching the logic.

## 4. Tests
`tests/ics.test.js`: escaping, fold + unfold round-trip, VCALENDAR/VEVENT
wrapping, UTC timestamp formatting, CRLF endings, optional-field omission, TEXT
escaping in `SUMMARY`. Planner wiring covered by mount-smoke; i18n parity by
`tests/i18n.test.js`.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: changing a shift changes the overlap, and
"Add to calendar" downloads a valid `meeting.ics` with matching `DTSTART`.
