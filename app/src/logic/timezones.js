// Spec 36 — cross-timezone meeting overlap. Pure math on UTC offsets (minutes
// east of UTC), so it is deterministic and DST-correct for whatever instant
// the offsets were resolved at. `zoneOffsetMinutes` reads a real IANA zone via
// Intl; the overlap math takes plain offsets so it is trivially testable.

// Offset in minutes east of UTC for an IANA zone at a given instant.
export function zoneOffsetMinutes(timeZone, now = Date.now()) {
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone, hourCycle: 'h23',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  })
  const p = Object.fromEntries(
    dtf.formatToParts(now).filter(x => x.type !== 'literal').map(x => [x.type, Number(x.value)])
  )
  const asUTC = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second)
  return Math.round((asUTC - Math.floor(now / 1000) * 1000) / 60000)
}

// Local hour-of-day (0..23, fractional for half-hour zones) for a UTC hour.
export function localHour(utcHour, offsetMinutes) {
  return ((((utcHour * 60 + offsetMinutes) % 1440) + 1440) % 1440) / 60
}

// UTC hours where BOTH parties are inside their working window [start, end).
export function overlapHours(offsetA, offsetB, opts = {}) {
  const { startA = 9, endA = 18, startB = 9, endB = 18 } = opts
  const within = (h, s, e) => h >= s && h < e
  const hours = []
  for (let u = 0; u < 24; u++) {
    if (within(localHour(u, offsetA), startA, endA) && within(localHour(u, offsetB), startB, endB)) {
      hours.push(u)
    }
  }
  return hours
}

// Middle of the overlap window — the most humane slot for both sides.
// Returns the UTC hour, or null when there is no overlap.
export function suggestSlot(hours) {
  if (!Array.isArray(hours) || hours.length === 0) return null
  return hours[Math.floor((hours.length - 1) / 2)]
}
