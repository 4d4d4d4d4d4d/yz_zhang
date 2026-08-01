// Spec 29 — Vue-side analytics wrapper over the pure recorder. Shared
// recorder; dev console.debug; no network in the demo.
// Spec 41 — gated on GDPR consent: nothing is recorded until the visitor
// opts in (privacy by default).
import { createRecorder } from '../logic/analytics.js'
import { canTrack } from '../logic/consent.js'
import { prefs } from '../store/workspace.js'

const recorder = createRecorder()

export function useAnalytics() {
  return {
    track(name, props = {}) {
      if (!canTrack('analytics', prefs.consent)) return null
      const e = recorder.record(name, props)
      if (typeof console !== 'undefined' && import.meta.env?.DEV) {
        console.debug('[analytics]', e.name, e.props)
      }
      return e
    },
    recorder
  }
}
