// Spec 29 — pure analytics event layer. Allowlisted event names (a typo'd
// funnel event is a silent data hole) + a testable ring-buffer recorder.

export const EVENTS = [
  'form_view', 'form_submit', 'form_error', 'form_success',
  'cta_click', 'page_view'
]

export function event(name, props = {}, now = Date.now()) {
  if (!EVENTS.includes(name)) throw new Error(`unknown analytics event "${name}"`)
  return { name, props, at: now }
}

export function createRecorder({ limit = 200 } = {}) {
  const buffer = []
  return {
    record(name, props, now = Date.now()) {
      const e = event(name, props, now)
      buffer.push(e)
      if (buffer.length > limit) buffer.shift() // ring buffer: drop oldest
      return e
    },
    all: () => [...buffer],
    countByName(name) {
      return buffer.filter(e => e.name === name).length
    },
    clear() { buffer.length = 0 }
  }
}
