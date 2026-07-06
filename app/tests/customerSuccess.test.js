import { describe, it, expect } from 'vitest'
import {
  scoreHealth, healthBand, churnProbability, enrichAccount,
  healthSummary, slaStatus, slaSummary, HEALTH_WEIGHTS
} from '../src/logic/customerSuccess.js'

describe('scoreHealth', () => {
  it('weighted sum over the fixture signals', () => {
    // 92*.3 + 100*.15 + 88*.15 + 84*.25 + 92*.15 = 27.6+15+13.2+21+13.8 = 90.6 → 91
    expect(scoreHealth({ usage: 92, payment: 100, support: 88, adoption: 84, sentiment: 92 })).toBe(91)
  })

  it('missing signals count as zero; unknown keys ignored', () => {
    expect(scoreHealth({ usage: 100 })).toBe(30) // only usage weight
    expect(scoreHealth({ usage: 100, bogus: 999 })).toBe(30)
  })

  it('accepts custom weights and stays within 0–100', () => {
    expect(scoreHealth({ usage: 100 }, { usage: 1 })).toBe(100)
    expect(scoreHealth({})).toBe(0)
  })
})

describe('healthBand', () => {
  it('thresholds are exact at 80 and 60', () => {
    expect(healthBand(80)).toBe('ok')
    expect(healthBand(79)).toBe('warn')
    expect(healthBand(60)).toBe('warn')
    expect(healthBand(59)).toBe('risk')
  })
})

describe('churnProbability', () => {
  it('healthy account far from renewal → low churn', () => {
    expect(churnProbability(95, 300)).toBeLessThan(10)
  })

  it('unhealthy account near renewal → high churn', () => {
    // base=.62, urgency=(120-20)/120=.833 → (.434+.25)*100 = 68
    expect(churnProbability(38, 20)).toBe(68)
  })

  it('renewal beyond 120 days adds no urgency (guard, not negative)', () => {
    expect(churnProbability(80, 300)).toBe(churnProbability(80, 120))
  })

  it('is bounded 0–100', () => {
    expect(churnProbability(0, 0)).toBeLessThanOrEqual(100)
    expect(churnProbability(100, 999)).toBe(0)
  })
})

describe('enrichAccount / healthSummary', () => {
  const accounts = [
    { name: 'A', mrr: 1000, signals: { usage: 96, payment: 100, support: 92, adoption: 90, sentiment: 92 }, renewalIn: 300 },
    { name: 'B', mrr: 5000, signals: { usage: 38, payment: 68, support: 52, adoption: 34, sentiment: 42 }, renewalIn: 40 }
  ]

  it('enriches with score, band and churn', () => {
    const e = enrichAccount(accounts[1])
    expect(e.band).toBe('risk')
    expect(e.churn).toBeGreaterThan(50)
  })

  it('summary rolls up band counts, MRR at risk and avg score', () => {
    const s = healthSummary(accounts)
    expect(s.total).toBe(2)
    expect(s.ok).toBe(1)
    expect(s.risk).toBe(1)
    expect(s.mrrAtRisk).toBe(5000)
    expect(s.avgScore).toBeGreaterThan(0)
  })

  it('empty portfolio is zero-safe', () => {
    expect(healthSummary([])).toMatchObject({ total: 0, avgScore: 0, mrrAtRisk: 0 })
  })
})

describe('slaStatus (injected now)', () => {
  const NOW = 1_000_000_000_000
  const h = n => new Date(NOW + n * 3600000).toISOString()

  it('breaches when past due and unresolved', () => {
    const s = slaStatus({ due: h(-2), sla: 8, status: 'active' }, NOW)
    expect(s.breach).toBe(true)
    expect(s.hoursLeft).toBeCloseTo(-2, 6)
  })

  it('resolved tickets are 100% consumed and never breach', () => {
    const s = slaStatus({ due: h(-5), sla: 8, status: 'resolved' }, NOW)
    expect(s.pctConsumed).toBe(100)
    expect(s.breach).toBe(false)
  })

  it('fresh ticket consumes proportionally (may be < 0 far out)', () => {
    // 6h left on an 8h SLA → 25% consumed
    expect(slaStatus({ due: h(6), sla: 8, status: 'active' }, NOW).pctConsumed).toBeCloseTo(25, 6)
  })

  it('is deterministic for a fixed now', () => {
    const t = { due: h(3), sla: 8, status: 'active' }
    expect(slaStatus(t, NOW)).toEqual(slaStatus(t, NOW))
  })
})

describe('slaSummary', () => {
  const NOW = 1_000_000_000_000
  const h = n => new Date(NOW + n * 3600000).toISOString()
  const tickets = [
    { due: h(-1), sla: 8, status: 'active', csat: null },
    { due: h(4), sla: 8, status: 'active', csat: null },
    { due: h(2), sla: 8, status: 'resolved', csat: 5 },
    { due: h(2), sla: 8, status: 'resolved', csat: 4 }
  ]

  it('counts active/breached/resolved and averages CSAT over rated only', () => {
    const s = slaSummary(tickets, NOW)
    expect(s.active).toBe(2)
    expect(s.breached).toBe(1)
    expect(s.resolved).toBe(2)
    expect(s.csat).toBe(4.5)
  })

  it('no rated tickets → csat null', () => {
    expect(slaSummary([{ due: h(1), sla: 8, status: 'active', csat: null }], NOW).csat).toBeNull()
  })
})
