# Spec 41 — Consent-Gated Analytics (GDPR)

**Status:** Accepted · **Depends on:** 29 (analytics), 27 (store)

## 1. Problem (critical analysis)

The site records analytics events (spec 29/30) **unconditionally**. For a
go-global product entering the EU that is both a GDPR violation and a missing
industry-standard surface — every compliant site gates optional tracking behind
a consent banner and lets the visitor withdraw as easily as they gave it. There
was no consent concept anywhere in the client.

## 2. Scope

- `logic/consent.js` — pure model: `defaultConsent` (privacy-by-default:
  undecided, analytics off), `normalizeConsent`, `canTrack(category, consent)`
  ('necessary' always true; optional categories require opt-in), `decide(choice)`
  (accept / reject / granular).
- `store/workspace.js` — persist a `consent` record; `setConsent` normalizes.
- `composables/useAnalytics.js` — **gate**: `track()` records nothing unless
  `canTrack('analytics', prefs.consent)`. The pure `createRecorder`/`event`
  layer is untouched, so unit tests that use it directly are unaffected.
- `ConsentBanner.vue` (mounted in `App.vue`) — shows until decided; Accept /
  Necessary-only. `Footer.vue` gains a **Privacy choices** link that reopens it
  (withdrawal as easy as consent). i18n across all four locales.

## 3. Review record

**R1 — gate the composable, not the pure layer.** Putting the check in
`useAnalytics` (not in `event()`) keeps `logic/analytics.js` pure and its tests
green, and keeps the consent dependency (store) out of the logic layer.

**R2 — privacy by default.** Until the visitor decides, `analytics` is false and
`track()` is a no-op — so the very first page-view isn't recorded pre-consent.
The demo funnel is empty until the visitor accepts, which is the correct,
honest behavior.

**R3 — withdrawable.** GDPR requires withdrawal to be as easy as granting. The
footer link resets `decided` to reopen the banner; choosing again re-persists.

## 4. Tests
`tests/consent.test.js`: default/normalize/`canTrack`/`decide` across accept,
reject, granular, and junk inputs. Store persistence via `tests/workspace.test.js`;
banner/footer wiring via mount-smoke; i18n parity via `tests/i18n.test.js`.
`tests/conversion.test.js` (spec 29) stays green — it exercises the pure recorder.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: pre-consent `track()` records nothing; Accept
enables it and the banner dismisses; the footer link brings it back.
