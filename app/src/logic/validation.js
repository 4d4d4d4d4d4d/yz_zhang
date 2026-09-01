// Spec 29 — pure form validation. Per-field, returns i18n message KEYS
// (the parity gate owns the copy), never strings.

// Pragmatic format check (local@domain.tld) — deliberately NOT a full
// RFC 5322 parser: over-strict email rules reject valid addresses and
// become their own conversion bug.
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

const REQUIRED = ['name', 'email', 'company', 'message']

export function validateContact(form = {}) {
  const errors = {}
  for (const field of REQUIRED) {
    if (!String(form[field] ?? '').trim()) errors[field] = 'contact.err.required'
  }
  if (!errors.email && !EMAIL_RE.test(String(form.email).trim())) {
    errors.email = 'contact.err.email'
  }
  return { valid: Object.keys(errors).length === 0, errors }
}
