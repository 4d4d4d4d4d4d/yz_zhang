# Spec 08 — Cross-Language Seamless Communication · Immersive Meetings
(跨语言无缝沟通 · 身临其境会议会谈)

Status: **Approved** · Review: R1 (2026-07-02)
Domains: `logic/interpreter.js`, `logic/meeting.js`

## Problem

Cross-border deals die in translation and time zones. Two engines:
(1) a live interpreter layer that translates every utterance while
**protecting brand/technical terminology**, and (2) a meeting scheduler
that finds humane overlap windows across attendee time zones so the
"immersive meeting room" (avatars + live captions) can actually convene.

## Design — interpreter

### Glossary protection — `applyGlossary(text, glossary, targetLang)`
- Glossary entries: `{ term, translations: {lang: fixed}, keep?: true }`.
  `keep: true` = never translate (product names). Longest-match-first so
  "AdForge Studio" wins over "AdForge". Case-insensitive match, original
  casing replaced by the fixed form. Returns `{ text, protected[] }` —
  the UI underlines protected terms so both sides see the enforcement.

### Caption routing — `routeCaption(utterance, session)`
- Session: `{ participants: [{ id, lang }] }`. An utterance fans out to
  one caption per participant; same-language listeners get `verbatim: true`
  (no round-trip). Each caption carries `{ to, lang, text, latencyMs }`
  with deterministic simulated latency = f(text length, language-pair
  distance class) — same-family pairs faster than cross-family.

## Design — meeting

### `overlapWindows(attendees, opts)`
- Attendees: `{ id, tz }` with tz as UTC offset in hours (fractional
  allowed: IST 5.5). Working hours default 08:00–20:00 local,
  configurable.
- Returns UTC hour windows `[startUtc, endUtc)` where **every** attendee
  is inside working hours, handling day wrap (a window may cross
  midnight UTC), ranked by a comfort score = min over attendees of
  distance from local 13:00 (midday-centered comfort).
- No overlap → `[]` plus `bestCompromise`: the window maximizing the
  count of in-hours attendees (so the UI can still propose something).

### Room capacity
- `createRoom(capacity)`: join/leave with hard cap; joining a full room
  returns `{ ok: false, reason: 'full' }` — never throws, never
  over-admits (concurrency posture per spec 00: bounded, explicit).

## Test plan
- Glossary: longest-match precedence, keep-terms survive, case handling.
- Routing: same-lang verbatim, fan-out count = participants − speaker,
  latency deterministic per pair class.
- Overlap: known 3-zone fixture (SH/Berlin/SF) yields expected windows;
  wrap-around window found; no-overlap returns bestCompromise; fractional
  offsets exact.
- Room: cap enforced under interleaved join/leave.

## Review record — R1
- ✅ `keep` terms added after review (product names were being localized).
- ✅ `bestCompromise` added: empty result with no proposal is a dead end
  for the operator.
- Verdict: **approved**.
