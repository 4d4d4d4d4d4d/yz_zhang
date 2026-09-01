// Spec 08 — immersive meeting: cross-timezone overlap windows + bounded room.

const DAY = 24

const mod24 = h => ((h % DAY) + DAY) % DAY

function inWorkingHours(utcHour, tz, startLocal, endLocal) {
  const local = mod24(utcHour + tz)
  return local >= startLocal && local < endLocal
}

// Comfort of a UTC hour for one attendee: 1 at local 13:00, falling linearly to 0 at ±12h.
function comfort(utcHour, tz) {
  const local = mod24(utcHour + tz)
  const dist = Math.min(Math.abs(local - 13), DAY - Math.abs(local - 13))
  return 1 - dist / 12
}

// Attendees: [{ id, tz }] with tz = UTC offset hours (fractional ok).
// Returns UTC windows where everyone is inside working hours, ranked by
// the worst attendee's comfort. Windows may wrap midnight UTC.
export function overlapWindows(attendees = [], { startLocal = 8, endLocal = 20, stepMinutes = 30 } = {}) {
  if (!attendees.length) return { windows: [], bestCompromise: null }
  const step = stepMinutes / 60
  const slots = []
  for (let h = 0; h < DAY; h += step) {
    const inside = attendees.filter(a => inWorkingHours(h, a.tz, startLocal, endLocal)).length
    slots.push({ h, all: inside === attendees.length, inside })
  }

  // Group consecutive all-in slots into windows (wrap-aware: rotate to a gap first).
  const firstGap = slots.findIndex(s => !s.all)
  const rotated = firstGap === -1 ? slots : [...slots.slice(firstGap), ...slots.slice(0, firstGap)]
  const windows = []
  let cur = null
  for (const s of rotated) {
    if (s.all) {
      if (!cur) cur = { startUtc: s.h, endUtc: s.h + step }
      else cur.endUtc = s.h + step
    } else if (cur) { windows.push(cur); cur = null }
  }
  if (cur) windows.push(cur)
  if (firstGap === -1 && windows.length) windows[0] = { startUtc: 0, endUtc: 24 }

  for (const w of windows) {
    w.startUtc = mod24(w.startUtc)
    w.endUtc = mod24(w.endUtc) === 0 && w.endUtc !== w.startUtc ? 24 : mod24(w.endUtc)
    // score = worst attendee comfort at window midpoint
    const mid = w.startUtc + (((w.endUtc - w.startUtc) + DAY) % DAY) / 2
    w.score = Math.min(...attendees.map(a => comfort(mid, a.tz)))
  }
  windows.sort((a, b) => b.score - a.score)

  let bestCompromise = null
  if (!windows.length) {
    let best = { inside: -1 }
    for (const s of slots) if (s.inside > best.inside) best = s
    bestCompromise = { startUtc: best.h, endUtc: best.h + step, attendeesIn: best.inside, of: attendees.length }
  }
  return { windows, bestCompromise }
}

// Bounded meeting room: join never over-admits, never throws.
export function createRoom(capacity) {
  if (!Number.isInteger(capacity) || capacity < 1) throw new Error('capacity must be a positive integer')
  const present = new Set()
  return {
    join(id) {
      if (present.has(id)) return { ok: true, already: true }
      if (present.size >= capacity) return { ok: false, reason: 'full' }
      present.add(id)
      return { ok: true }
    },
    leave(id) { return { ok: present.delete(id) } },
    size: () => present.size,
    capacity
  }
}
