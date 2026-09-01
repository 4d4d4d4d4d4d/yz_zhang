# Spec 29 — Conversion Surface Hardening (batch): Form Validation · A11y Errors · Analytics Funnel

Status: **Approved** · Review: R1 (2026-07-07)
Domains: `logic/validation.js` · `logic/analytics.js` ·
`composables/useAnalytics.js` (+ rewired `Contact.vue`)

## Problem (v24 critical review)

The Contact form is the primary conversion surface — the partner sign-up
that the whole GTM funnel drives toward — and it is the weakest-validated
code in the app:

- `valid` is `name && email && company && message` truthiness. Email
  `"x"` passes; there is no format check, no per-field error, nothing
  telling the user *which* field is wrong.
- The error state (`status === 'error'`) is a single generic banner with
  no `aria-invalid`, no `aria-describedby`, no `role="alert"` — invisible
  to a screen reader on the one form that matters most.
- There is **no analytics layer at all**. You cannot optimize a funnel
  you don't measure; every real product tracks form-view / submit /
  error / success. There is nothing to build funnel metrics on later.

## Design

### `logic/validation.js` — pure, per-field
- `EMAIL_RE`: a pragmatic RFC-lite pattern (local@domain.tld, no spaces,
  a dotted TLD ≥ 2 chars). Documented as deliberately permissive-but-
  format-checking, not a full RFC 5322 parser.
- `validateContact(form)` → `{ valid, errors }` where `errors` maps each
  failing field to a message **key** (`contact.err.required` /
  `contact.err.email`), never a string — the parity gate owns the copy.
  Required: name, email, company, message. Email additionally
  format-checked. `region`/`role` optional.
- Total and pure: missing fields treated as empty; never throws.

### `logic/analytics.js` — pure event layer
- `event(name, props)` builds a normalized `{ name, props, at }` after
  validating `name` against an `EVENTS` allowlist (unknown name throws in
  dev — a typo'd funnel event is a silent data hole).
- `createRecorder({ limit })`: an in-memory ring buffer (`record`,
  `all`, `countByName`) — the testable core. Production would fan events
  to a real sink; the demo keeps them in memory.

### `composables/useAnalytics.js`
Thin Vue-side wrapper exposing `track(name, props)` that records to a
shared recorder and (dev) `console.debug`s. No network in the demo.

### `Contact.vue` rewiring
- On submit, `validateContact` drives per-field state: each input gets
  `aria-invalid` and `aria-describedby` pointing at a per-field
  `role="alert"` message; focus moves to the first invalid field.
- Fires `form_view` on mount, `form_submit` on attempt, `form_error`
  (with the invalid field list) or `form_success` on outcome.
- Existing generic banner kept as a summary, now `role="status"`.

## Test plan
- validation: all-valid passes; each required field missing → its key;
  bad emails (`x`, `a@b`, `a@b.c`? borderline) rejected, good emails
  accepted; region/role optional.
- analytics: `event` normalizes + timestamps; unknown name throws;
  recorder ring-buffer evicts oldest past limit; countByName correct.
- Browser: submitting empty focuses the first invalid field and the
  screen-reader alert text is present; a malformed email is rejected
  while a good one submits; the recorder shows view→submit→error→success.

## Review record — R1
- ✅ Email regex scoped as "format check, not RFC parser" — over-strict
  email validation rejects valid addresses and is its own conversion bug.
- ✅ Analytics event names allowlisted so a typo fails loudly in dev
  rather than dropping funnel data silently.
- ✅ Errors carry i18n keys, focus management moves to first invalid —
  a11y and UX handled together on the surface that most needs them.
- Verdict: **approved**.
