import { describe, it, expect } from 'vitest'
import { zoneOffsetMinutes, localHour, overlapHours, suggestSlot } from '../src/logic/timezones.js'

describe('zoneOffsetMinutes', () => {
  it('is 0 for UTC', () => {
    expect(zoneOffsetMinutes('UTC', Date.UTC(2026, 0, 15, 12))).toBe(0)
  })
  it('is +540 for Asia/Tokyo (JST, no DST)', () => {
    expect(zoneOffsetMinutes('Asia/Tokyo', Date.UTC(2026, 0, 15, 12))).toBe(540)
  })
})

describe('localHour', () => {
  it('shifts a UTC hour by a positive offset', () => {
    expect(localHour(1, 540)).toBe(10) // 01:00 UTC = 10:00 JST
  })
  it('wraps across midnight for negative offsets', () => {
    expect(localHour(2, -300)).toBe(21) // 02:00 UTC = 21:00 previous day EST
  })
  it('handles half-hour zones', () => {
    expect(localHour(0, 330)).toBe(5.5) // IST +5:30
  })
})

describe('overlapHours', () => {
  it('finds the working-hours overlap between two zones', () => {
    // A at +540 (Tokyo), B at 0 (London), both 9–18 local
    const hrs = overlapHours(540, 0)
    // Tokyo 9–18 = UTC 0–9; London 9–18 = UTC 9–18; overlap is empty-ish
    for (const u of hrs) {
      expect(localHour(u, 540)).toBeGreaterThanOrEqual(9)
      expect(localHour(u, 540)).toBeLessThan(18)
      expect(localHour(u, 0)).toBeGreaterThanOrEqual(9)
      expect(localHour(u, 0)).toBeLessThan(18)
    }
  })
  it('is symmetric in count', () => {
    expect(overlapHours(60, -300).length).toBe(overlapHours(-300, 60).length)
  })
  it('gives a full window for identical zones', () => {
    expect(overlapHours(0, 0)).toEqual([9, 10, 11, 12, 13, 14, 15, 16, 17])
  })
  it('respects custom working windows', () => {
    expect(overlapHours(0, 0, { startA: 8, endA: 10, startB: 9, endB: 12 })).toEqual([9])
  })
  it('returns empty when windows never align', () => {
    // Same zone, disjoint working windows → no shared hour
    expect(overlapHours(0, 0, { startA: 0, endA: 6, startB: 12, endB: 18 })).toEqual([])
  })
})

describe('suggestSlot', () => {
  it('picks the middle of the window', () => {
    expect(suggestSlot([9, 10, 11, 12, 13])).toBe(11)
  })
  it('picks the lower-middle for an even count', () => {
    expect(suggestSlot([10, 11, 12, 13])).toBe(11)
  })
  it('is null with no overlap', () => {
    expect(suggestSlot([])).toBeNull()
    expect(suggestSlot(null)).toBeNull()
  })
})
