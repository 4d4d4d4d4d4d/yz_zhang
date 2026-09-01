import { describe, it, expect } from 'vitest'
import { deriveAlerts, createInbox } from '../src/logic/notifications.js'
import { slaSummary, healthSummary } from '../src/logic/customerSuccess.js'
import { assessCampaign } from '../src/logic/riskLegal.js'
import { invoice } from '../src/logic/metering.js'
import { dealReadiness } from '../src/logic/pipeline.js'

// Spec 26 — derivation is fed by REAL engine outputs (spec-19 pattern).

const NOW = 1_000_000_000_000
const h = n => new Date(NOW + n * 3600000).toISOString()

describe('deriveAlerts from real domain outputs', () => {
  it('SLA breach → critical with the support deep link', () => {
    const sla = slaSummary([{ due: h(-2), sla: 8, status: 'active', csat: null }], NOW)
    expect(sla.breached).toBe(1)
    const [a] = deriveAlerts({ sla })
    expect(a).toMatchObject({ key: 'sla-breach', severity: 'critical' })
    expect(a.route.query.sub).toBe('support')
    expect(a.params.count).toBe(1)
  })

  it('churn risk → warning carrying count and MRR at risk', () => {
    const health = healthSummary([
      { name: 'A', mrr: 5000, signals: { usage: 30, payment: 60, support: 40, adoption: 30, sentiment: 40 }, renewalIn: 30 }
    ])
    const [a] = deriveAlerts({ health })
    expect(a.severity).toBe('warning')
    expect(a.params).toMatchObject({ count: 1, mrr: 5000 })
  })

  it('compliance block → critical; review → warning', () => {
    const block = assessCampaign({ markets: ['EU'], attributes: { dpa: true, localization: true, ageGate: true, adDisclosure: true, provenance: true } })
    expect(block.gate).toBe('block') // consent missing
    expect(deriveAlerts({ compliance: block })[0].severity).toBe('critical')
    const review = assessCampaign({ markets: ['EU'], attributes: { consent: true, dpa: true, localization: true, adDisclosure: true, provenance: true } })
    expect(review.gate).toBe('review') // ageGate missing
    expect(deriveAlerts({ compliance: review })[0].severity).toBe('warning')
  })

  it('metering overage and stalled readiness produce their alerts', () => {
    const inv = invoice(1000, [{ used: 1250, included: 1000, cost: 500 }])
    const readiness = dealReadiness({ reels: [] })
    const alerts = deriveAlerts({ invoice: inv, readiness })
    expect(alerts.map(a => a.key)).toEqual(['metering-overage', 'deal-readiness'])
    expect(alerts[1].severity).toBe('info')
  })

  it('healthy inputs and missing inputs produce no alerts', () => {
    expect(deriveAlerts({})).toEqual([])
    const cleanSla = slaSummary([{ due: h(5), sla: 8, status: 'active', csat: null }], NOW)
    const passing = assessCampaign({ markets: ['SG'], attributes: { consent: true } })
    expect(deriveAlerts({ sla: cleanSla, compliance: passing })).toEqual([])
  })
})

describe('inbox', () => {
  const alert = (key, severity = 'info') => ({ key, severity, msgKey: 'x', params: {}, route: {} })

  it('dedupes by key: repeat updates timestamp and count', () => {
    const box = createInbox()
    box.push(alert('a'), 100)
    box.push(alert('a'), 200)
    expect(box.size()).toBe(1)
    const [item] = box.list()
    expect(item.count).toBe(2)
    expect(item.at).toBe(200)
  })

  it('unread tracking: markRead / markAllRead / unreadCount', () => {
    const box = createInbox()
    box.push(alert('a'), 1); box.push(alert('b'), 2)
    expect(box.unreadCount()).toBe(2)
    box.markRead('a')
    expect(box.unreadCount()).toBe(1)
    expect(box.list({ unreadOnly: true }).map(i => i.key)).toEqual(['b'])
    box.markAllRead()
    expect(box.unreadCount()).toBe(0)
  })

  it('lists newest first', () => {
    const box = createInbox()
    box.push(alert('old'), 1); box.push(alert('new'), 2)
    expect(box.list().map(i => i.key)).toEqual(['new', 'old'])
  })

  it('eviction removes oldest READ items and never drops unread', () => {
    const box = createInbox({ limit: 2 })
    box.push(alert('r1'), 1); box.markRead('r1')
    box.push(alert('u1'), 2)
    box.push(alert('u2'), 3) // over cap → r1 (read) evicted
    expect(box.size()).toBe(2)
    expect(box.list().map(i => i.key).sort()).toEqual(['u1', 'u2'])

    box.push(alert('u3'), 4) // all unread, over cap — nothing droppable
    expect(box.size()).toBe(3) // soft cap: unread never silently lost
    expect(box.unreadCount()).toBe(3)
  })
})
