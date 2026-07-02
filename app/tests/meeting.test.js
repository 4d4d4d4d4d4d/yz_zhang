import { describe, it, expect } from 'vitest'
import { overlapWindows, createRoom } from '../src/logic/meeting.js'

describe('overlapWindows', () => {
  it('SH/Berlin/SF have no common window — compromise proposed instead', () => {
    // 8–20 local → in-hours UTC: SH(+8) [0,12), Berlin(+2) [6,18), SF(−7) [15,24)∪[0,3).
    // SH ∩ Berlin = [6,12), which misses SF entirely → no full window.
    const { windows, bestCompromise } = overlapWindows([
      { id: 'sh', tz: 8 }, { id: 'ber', tz: 2 }, { id: 'sf', tz: -7 }
    ])
    expect(windows).toEqual([])
    expect(bestCompromise).not.toBeNull()
    expect(bestCompromise.attendeesIn).toBe(2)
  })

  it('two compatible zones produce a ranked window with local times inside hours', () => {
    const { windows } = overlapWindows([{ id: 'sh', tz: 8 }, { id: 'tk', tz: 9 }])
    expect(windows.length).toBeGreaterThan(0)
    const w = windows[0]
    for (const tz of [8, 9]) {
      const local = (w.startUtc + tz + 24) % 24
      expect(local).toBeGreaterThanOrEqual(8)
      expect(local).toBeLessThan(20)
    }
  })

  it('handles fractional offsets (IST +5.5)', () => {
    const { windows } = overlapWindows([{ id: 'ist', tz: 5.5 }, { id: 'sg', tz: 8 }])
    expect(windows.length).toBeGreaterThan(0)
  })

  it('single attendee: whole working day is a window', () => {
    const { windows } = overlapWindows([{ id: 'solo', tz: 0 }])
    expect(windows).toHaveLength(1)
    expect(windows[0].endUtc - windows[0].startUtc).toBeCloseTo(12, 5)
  })

  it('empty attendees → no windows, no compromise', () => {
    expect(overlapWindows([])).toEqual({ windows: [], bestCompromise: null })
  })

  it('wrap-around: zones straddling the date line still find their window', () => {
    // NZ (+12) in-hours UTC 20–8 (wraps); HST (-10) in-hours UTC 18–6 (wraps) → overlap 20–6 wraps midnight
    const { windows } = overlapWindows([{ id: 'nz', tz: 12 }, { id: 'hst', tz: -10 }])
    expect(windows.length).toBeGreaterThan(0)
    const w = windows[0]
    const width = ((w.endUtc - w.startUtc) + 24) % 24
    expect(width).toBeCloseTo(10, 1)
  })
})

describe('createRoom', () => {
  it('never over-admits and reports full instead of throwing', () => {
    const room = createRoom(2)
    expect(room.join('a').ok).toBe(true)
    expect(room.join('b').ok).toBe(true)
    expect(room.join('c')).toEqual({ ok: false, reason: 'full' })
    expect(room.size()).toBe(2)
  })

  it('rejoin is idempotent; leave frees a seat', () => {
    const room = createRoom(1)
    expect(room.join('a').ok).toBe(true)
    expect(room.join('a')).toEqual({ ok: true, already: true })
    room.leave('a')
    expect(room.join('b').ok).toBe(true)
  })

  it('rejects invalid capacity', () => {
    expect(() => createRoom(0)).toThrow()
  })
})
