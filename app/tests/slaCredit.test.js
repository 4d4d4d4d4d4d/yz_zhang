import { describe, it, expect } from 'vitest'
import { uptimeFromDowntime, serviceCredit, creditAmount, slaReport, DEFAULT_SCHEDULE } from '../src/logic/slaCredit.js'

describe('uptimeFromDowntime', () => {
  it('computes uptime from downtime over a period', () => {
    expect(uptimeFromDowntime(0, 43200)).toBe(100)
    expect(uptimeFromDowntime(43.2, 43200)).toBeCloseTo(99.9, 5)
  })
  it('clamps and guards bad input', () => {
    expect(uptimeFromDowntime(100, 0)).toBe(100)      // no period → assume full uptime
    expect(uptimeFromDowntime(99999, 43200)).toBe(0)  // more downtime than period → 0
    expect(uptimeFromDowntime(-5, 43200)).toBe(100)   // negative downtime ignored
  })
})

describe('serviceCredit', () => {
  it('is zero when the commitment is met', () => {
    expect(serviceCredit(99.95, { commitment: 99.9 })).toBe(0)
    expect(serviceCredit(99.9, { commitment: 99.9 })).toBe(0)
  })
  it('tiers the credit by how far short uptime fell', () => {
    expect(serviceCredit(99.85, { commitment: 99.9 })).toBe(10) // [99.0, 99.9)
    expect(serviceCredit(97.0, { commitment: 99.9 })).toBe(25)  // [95.0, 99.0)
    expect(serviceCredit(90.0, { commitment: 99.9 })).toBe(50)  // < 95.0
  })
  it('honours a custom schedule', () => {
    const schedule = [{ minUptime: 99.5, credit: 5 }, { minUptime: 0, credit: 100 }]
    expect(serviceCredit(99.6, { commitment: 99.99, schedule })).toBe(5)
    expect(serviceCredit(10, { commitment: 99.99, schedule })).toBe(100)
  })
  it('falls back to the lowest tier when no floor is cleared', () => {
    const schedule = [{ minUptime: 50, credit: 30 }]
    expect(serviceCredit(10, { commitment: 99.9, schedule })).toBe(30)
    expect(serviceCredit(10, { commitment: 99.9, schedule: [] })).toBe(0)
  })
})

describe('creditAmount', () => {
  it('applies the credit % to the monthly fee', () => {
    expect(creditAmount(12000, 10)).toBe(1200)
    expect(creditAmount(0, 25)).toBe(0)
    expect(creditAmount('bad', 10)).toBe(0)
  })
})

describe('slaReport', () => {
  it('summarizes a breached period', () => {
    const r = slaReport({ uptimePct: 99.85, commitment: 99.9, monthlyFee: 12000 })
    expect(r).toEqual({ uptimePct: 99.85, commitment: 99.9, met: false, creditPct: 10, creditAmount: 1200 })
  })
  it('summarizes a met period', () => {
    const r = slaReport({ uptimePct: 99.99, commitment: 99.9, monthlyFee: 12000 })
    expect(r.met).toBe(true)
    expect(r.creditPct).toBe(0)
    expect(r.creditAmount).toBe(0)
  })
  it('has a sane default schedule', () => {
    expect(DEFAULT_SCHEDULE.map(t => t.credit)).toEqual([10, 25, 50])
  })
})
