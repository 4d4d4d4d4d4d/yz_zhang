// Spec 29 — Vue-side analytics wrapper over the pure recorder. Shared
// recorder; dev console.debug; no network in the demo.
import { createRecorder } from '../logic/analytics.js'

const recorder = createRecorder()

export function useAnalytics() {
  return {
    track(name, props = {}) {
      const e = recorder.record(name, props)
      if (typeof console !== 'undefined' && import.meta.env?.DEV) {
        console.debug('[analytics]', e.name, e.props)
      }
      return e
    },
    recorder
  }
}
