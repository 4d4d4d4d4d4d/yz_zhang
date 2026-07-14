// Spec 27 — reactive workspace store with localStorage persistence.
// Vue `reactive` + localStorage only: one new concept, zero new deps.

import { reactive, computed } from 'vue'
import { deriveAlerts, createInbox } from '../logic/notifications.js'
import { slaSummary, healthSummary } from '../logic/customerSuccess.js'
import { assessCampaign } from '../logic/riskLegal.js'
import { invoice } from '../logic/metering.js'
import { dealReadiness } from '../logic/pipeline.js'
import { trustScore } from '../logic/showcase.js'
import { ACCOUNTS, ticketsAt, METERS, PLAN_BASE_FEES, TENANTS, CAMPAIGN, DEAL } from '../data/workspace.js'

const STORAGE_KEY = 'adforge.prefs'

function loadPrefs() {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return {
      currency: typeof parsed.currency === 'string' ? parsed.currency : null,
      readKeys: Array.isArray(parsed.readKeys) ? parsed.readKeys : []
    }
  } catch {
    // Malformed storage falls back to defaults — never throw at import time.
    return { currency: null, readKeys: [] }
  }
}

export const prefs = reactive(loadPrefs())

function persist() {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify({
      currency: prefs.currency,
      readKeys: prefs.readKeys
    }))
  } catch { /* storage unavailable (private mode) — stay in-memory */ }
}

export function setCurrencyPref(code) {
  prefs.currency = code
  persist()
}

// ------------------------------------------------------------- inbox

// Derive alerts by running the REAL engines over the single-source
// workspace data — the bell shows the same facts as the module pages.
export function deriveWorkspaceAlerts(now = Date.now()) {
  const flagship = TENANTS[0]
  return deriveAlerts({
    sla: slaSummary(ticketsAt(now), now),
    health: healthSummary(ACCOUNTS),
    compliance: assessCampaign(CAMPAIGN),
    invoice: invoice(PLAN_BASE_FEES[flagship.plan], METERS[flagship.id]),
    readiness: dealReadiness({
      reels: [trustScore(DEAL.reelEvidence)],
      fieldCase: DEAL.fieldCase,
      compliance: DEAL.compliance,
      diligence: DEAL.diligence,
      terms: DEAL.terms
    })
  })
}

let inboxSingleton = null
const inboxState = reactive({ version: 0 })

export function useInbox(now = Date.now()) {
  if (!inboxSingleton) {
    inboxSingleton = createInbox()
    for (const a of deriveWorkspaceAlerts(now)) inboxSingleton.push(a, now)
    for (const key of prefs.readKeys) inboxSingleton.markRead(key)
  }
  const box = inboxSingleton
  return {
    items: computed(() => { void inboxState.version; return box.list() }),
    unread: computed(() => { void inboxState.version; return box.unreadCount() }),
    markRead(key) {
      box.markRead(key)
      if (!prefs.readKeys.includes(key)) prefs.readKeys.push(key)
      persist()
      inboxState.version++
    },
    markAllRead() {
      box.markAllRead()
      prefs.readKeys = [...new Set([...prefs.readKeys, ...box.list().map(i => i.key)])]
      persist()
      inboxState.version++
    }
  }
}

// Test hook: reset module-level state between cases.
export function __resetForTests() {
  inboxSingleton = null
  inboxState.version = 0
  const fresh = loadPrefs()
  prefs.currency = fresh.currency
  prefs.readKeys = fresh.readKeys
}
