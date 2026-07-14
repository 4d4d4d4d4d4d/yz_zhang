import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ACCOUNTS, ticketsAt, TENANTS, METERS, PLAN_BASE_FEES } from '../src/data/workspace.js'
import { prefs, setCurrencyPref, useInbox, deriveWorkspaceAlerts, __resetForTests } from '../src/store/workspace.js'
import { slaSummary } from '../src/logic/customerSuccess.js'
import ModuleBoundary from '../src/components/ModuleBoundary.vue'
import en from '../src/i18n/locales/en.js'

const NOW = 1_000_000_000_000

beforeEach(() => {
  localStorage.clear()
  __resetForTests()
})

describe('workspace fixtures — single source of truth invariants', () => {
  it('account names are unique and carry full signal sets', () => {
    const names = ACCOUNTS.map(a => a.name)
    expect(new Set(names).size).toBe(names.length)
    for (const a of ACCOUNTS) {
      expect(Object.keys(a.signals).sort()).toEqual(['adoption', 'payment', 'sentiment', 'support', 'usage'])
    }
  })

  it('every tenant has meters and a known plan fee', () => {
    for (const t of TENANTS) {
      expect(METERS[t.id]?.length, t.id).toBeGreaterThan(0)
      expect(PLAN_BASE_FEES[t.plan], t.plan).toBeDefined()
    }
  })

  it('tickets materialize against an injected now (time stays testable)', () => {
    const tickets = ticketsAt(NOW)
    expect(tickets).toHaveLength(8)
    const t8241 = tickets.find(t => t.id === 'T-8241')
    expect(new Date(t8241.due).getTime()).toBe(NOW - 0.5 * 3600000)
    expect(t8241.dueInHours).toBeUndefined() // offsets don't leak
  })

  it('the fixture truth: 2 active tickets are past SLA', () => {
    expect(slaSummary(ticketsAt(NOW), NOW).breached).toBe(2)
  })
})

describe('store — persistence and shared inbox', () => {
  it('currency preference persists to localStorage', () => {
    setCurrencyPref('JPY')
    expect(JSON.parse(localStorage.getItem('adforge.prefs')).currency).toBe('JPY')
  })

  it('inbox derives from workspace data via real engines (same facts as the pages)', () => {
    const alerts = deriveWorkspaceAlerts(NOW)
    const byKey = Object.fromEntries(alerts.map(a => [a.key, a]))
    expect(byKey['sla-breach'].params.count).toBe(2) // matches the fixture truth above
    expect(byKey['churn-risk'].params.mrr).toBe(980)  // Mizu Logistics
    expect(byKey['metering-overage']).toBeDefined()   // lumi renders over allowance
  })

  it('markRead persists and survives a simulated reload', () => {
    const inbox = useInbox(NOW)
    const before = inbox.unread.value
    inbox.markRead('sla-breach')
    expect(inbox.unread.value).toBe(before - 1)

    // simulated reload: module state reset, localStorage kept
    const saved = localStorage.getItem('adforge.prefs')
    __resetForTests()
    localStorage.setItem('adforge.prefs', saved)
    __resetForTests()

    const fresh = useInbox(NOW)
    expect(fresh.unread.value).toBe(before - 1)
    expect(fresh.items.value.find(i => i.key === 'sla-breach').read).toBe(true)
  })

  it('malformed storage falls back to defaults, never throws', () => {
    localStorage.setItem('adforge.prefs', '{corrupt json!!')
    __resetForTests()
    expect(prefs.readKeys).toEqual([])
    expect(prefs.currency).toBeNull()
  })
})

describe('ModuleBoundary', () => {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

  const Bomb = { setup() { throw new Error('kaboom') }, template: '<div/>' }
  const Fine = { template: '<div class="fine">healthy</div>' }

  it('a throwing child renders the fallback card, not a blank tree', async () => {
    const wrapper = mount(ModuleBoundary, {
      global: { plugins: [i18n] },
      slots: { default: Bomb }
    })
    await wrapper.vm.$nextTick() // fallback re-renders on the tick after capture
    expect(wrapper.text()).toContain('This module hit an error')
    expect(wrapper.text()).toContain('kaboom')
  })

  it('a healthy child renders untouched', () => {
    const wrapper = mount(ModuleBoundary, {
      global: { plugins: [i18n] },
      slots: { default: Fine }
    })
    expect(wrapper.find('.fine').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('error')
  })
})
