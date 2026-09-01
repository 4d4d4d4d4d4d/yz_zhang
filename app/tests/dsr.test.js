import { describe, it, expect } from 'vitest'
import { regimeDays, dueAt, createDSR, dsrStatus, hoursRemaining, summarizeDSR, REGIME_DAYS } from '../src/logic/dsr.js'

const DAY = 86400000

describe('regimeDays', () => {
  it('knows the statutory windows', () => {
    expect(regimeDays('GDPR')).toBe(30)
    expect(regimeDays('CCPA')).toBe(45)
    expect(regimeDays('APPI')).toBe(14)
  })
  it('falls back to the strictest common default (30) for unknown regimes', () => {
    expect(regimeDays('MARS')).toBe(30)
  })
})

describe('dueAt / createDSR', () => {
  it('sets the deadline from regime + receivedAt', () => {
    const req = createDSR({ id: 'D1', type: 'access', regime: 'CCPA', receivedAt: 0 })
    expect(req.dueAt).toBe(45 * DAY)
    expect(dueAt('GDPR', 1000)).toBe(1000 + 30 * DAY)
  })
  it('defaults receivedAt to the injected now when omitted', () => {
    const req = createDSR({ id: 'D2', regime: 'GDPR' }, 5000)
    expect(req.receivedAt).toBe(5000)
    expect(req.dueAt).toBe(5000 + 30 * DAY)
  })
})

describe('dsrStatus', () => {
  const base = createDSR({ id: 'D', type: 'access', regime: 'GDPR', receivedAt: 0 }) // due at 30d

  it('is open well before the deadline', () => {
    expect(dsrStatus(base, 10 * DAY)).toBe('open')
  })
  it('is due_soon within 7 days', () => {
    expect(dsrStatus(base, 25 * DAY)).toBe('due_soon')
  })
  it('is overdue past the deadline', () => {
    expect(dsrStatus(base, 31 * DAY)).toBe('overdue')
  })
  it('keeps a resolution regardless of time', () => {
    expect(dsrStatus({ ...base, resolution: 'fulfilled' }, 999 * DAY)).toBe('fulfilled')
    expect(dsrStatus({ ...base, resolution: 'rejected' }, 0)).toBe('rejected')
  })
})

describe('hoursRemaining', () => {
  it('counts down whole hours', () => {
    const req = createDSR({ id: 'D', type: 'access', regime: 'GDPR', receivedAt: 0 })
    expect(hoursRemaining(req, 30 * DAY - 3600000)).toBe(1)
  })
  it('clamps to 0 once overdue', () => {
    const req = createDSR({ id: 'D', type: 'access', regime: 'APPI', receivedAt: 0 })
    expect(hoursRemaining(req, 100 * DAY)).toBe(0)
  })
})

describe('summarizeDSR', () => {
  it('tallies by derived status', () => {
    const reqs = [
      createDSR({ id: 'a', regime: 'GDPR', receivedAt: 0 }),                    // open at 10d
      createDSR({ id: 'b', regime: 'APPI', receivedAt: 0 }),                    // overdue at 10d (14d... no, 10<14 open)
      createDSR({ id: 'c', regime: 'LGPD', receivedAt: 0 }),                    // 15d window → due_soon at 10d
      { ...createDSR({ id: 'd', regime: 'GDPR', receivedAt: 0 }), resolution: 'fulfilled' }
    ]
    const s = summarizeDSR(reqs, 10 * DAY)
    expect(s.total).toBe(4)
    expect(s.resolved).toBe(1)
    expect(s.open + s.due_soon + s.overdue).toBe(3)
  })
  it('guards a non-array', () => {
    expect(summarizeDSR(null, 0)).toEqual({ total: 0, open: 0, due_soon: 0, overdue: 0, resolved: 0 })
  })
})

describe('REGIME_DAYS', () => {
  it('covers the major regimes', () => {
    expect(Object.keys(REGIME_DAYS)).toEqual(expect.arrayContaining(['GDPR', 'CCPA', 'LGPD', 'APPI']))
  })
})
