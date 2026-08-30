// Spec 59 — what to warm after the reader lands on a console section.
//
// Prefetching everything is the same mistake as bundling everything, one
// network hop later: it spends the reader's bandwidth on six sections to save
// a click on one. So the policy is deliberately small and evidence-led.
//   1. Where they have actually been (MRU, most recent first) — the strongest
//      signal we have, because console work is back-and-forth between two or
//      three modules, not a linear tour.
//   2. Then the sidebar neighbours of where they are, since the nav is the
//      only other affordance in reach.
// Capped, and never the active section — that one is already loading.

export function prefetchOrder(allKeys = [], activeKey, recents = [], { max = 2 } = {}) {
  const known = new Set(allKeys)
  const out = []
  const take = key => {
    if (key === activeKey || !known.has(key) || out.includes(key)) return
    if (out.length < max) out.push(key)
  }

  for (const key of recents) take(key)

  const i = allKeys.indexOf(activeKey)
  if (i !== -1) {
    take(allKeys[i + 1])
    take(allKeys[i - 1])
  }
  return out
}

// Idle scheduling with the globals injected, so a test can drive it and a
// server-side or old runtime without requestIdleCallback still fires.
export function idleSchedule(g = globalThis) {
  if (typeof g.requestIdleCallback === 'function') {
    return cb => g.requestIdleCallback(cb, { timeout: 2000 })
  }
  if (typeof g.setTimeout === 'function') return cb => g.setTimeout(cb, 200)
  return cb => cb()
}

export function requestIdle(fn, schedule = idleSchedule()) {
  return schedule(() => { try { fn() } catch { /* speculative work must never surface */ } })
}
