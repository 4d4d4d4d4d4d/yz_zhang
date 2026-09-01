// Spec 39 — action commands for the ⌘K palette. Pure descriptors only: the
// palette resolves the label via i18n and executes via injected handlers, so
// this stays framework-free (spec 00 §2) and trivially testable.

export function buildActionCommands({ locales = [], motionPrefs = [] } = {}) {
  const acts = []
  for (const code of locales) acts.push({ id: `act:locale:${code}`, kind: 'locale', arg: code })
  for (const pref of motionPrefs) acts.push({ id: `act:motion:${pref}`, kind: 'motion', arg: pref })
  return acts
}
