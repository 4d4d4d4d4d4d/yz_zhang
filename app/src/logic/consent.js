// Spec 41 — GDPR-style consent model. Pure. "necessary" cookies are always
// permitted; optional categories (analytics) require an explicit opt-in.
// Privacy by default: until the visitor decides, optional tracking is off.

export const OPTIONAL_CATEGORIES = ['analytics']

export function defaultConsent() {
  return { analytics: false, decided: false }
}

// Sanitize a persisted/untrusted value into a known shape.
export function normalizeConsent(raw) {
  if (!raw || typeof raw !== 'object') return defaultConsent()
  return { analytics: Boolean(raw.analytics), decided: Boolean(raw.decided) }
}

// May we record for this category given the consent state?
export function canTrack(category, consent) {
  if (category === 'necessary') return true
  return Boolean(consent && consent[category])
}

// Turn a banner choice into a decided consent record. 'accept' opts into all
// optional categories, 'reject' into none; an object grants explicitly.
export function decide(choice) {
  if (choice === 'accept') return { analytics: true, decided: true }
  if (choice === 'reject') return { analytics: false, decided: true }
  return { analytics: Boolean(choice && choice.analytics), decided: true }
}
