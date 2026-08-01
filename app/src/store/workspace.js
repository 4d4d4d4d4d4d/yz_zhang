// Spec 27 — reactive workspace store with localStorage persistence.
// Vue `reactive` + localStorage only: one new concept, zero new deps.

import { reactive, computed } from 'vue'
import { pushRecent } from '../logic/recents.js'
import { normalizeConsent, defaultConsent } from '../logic/consent.js'
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
      readKeys: Array.isArray(parsed.readKeys) ? parsed.readKeys : [],
      recents: Array.isArray(parsed.recents) ? parsed.recents.filter(k => typeof k === 'string') : [],
      motion: typeof parsed.motion === 'string' ? parsed.motion : 'system',
      consent: normalizeConsent(parsed.consent)
    }
  } catch {
    // Malformed storage falls back to defaults — never throw at import time.
    return { currency: null, readKeys: [], recents: [], motion: 'system', consent: defaultConsent() }
  }
}

export const prefs = reactive(loadPrefs())

function persist() {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify({
      currency: prefs.currency,
      readKeys: prefs.readKeys,
      recents: prefs.recents,
      motion: prefs.motion,
      consent: prefs.consent
    }))
  } catch { /* storage unavailable (private mode) — stay in-memory */ }
}

export function setCurrencyPref(code) {
  prefs.currency = code
  persist()
}

// Spec 32 — record the most-recently-visited console section (MRU) so the
// ⌘K palette can offer them on an empty query. Keys are opaque; the view
// filters to registry-valid ones on read.
export function recordSection(key) {
  const next = pushRecent(prefs.recents, key)
  prefs.recents.splice(0, prefs.recents.length, ...next)
  persist()
}

// Spec 38 — persisted motion preference ('system' | 'reduce' | 'full').
export function setMotionPref(value) {
  prefs.motion = value
  persist()
}

// Spec 41 — persisted GDPR consent record.
export function setConsent(next) {
  prefs.consent = normalizeConsent(next)
  persist()
}

// ------------------------------------------------------------- inbox

// Derive alerts by running the REAL engines over the single-source
// workspace data — the bell shows the same facts as the module pages.
// Single-source deal readiness: the notification bell (via deriveWorkspaceAlerts)
// and the exportable deal report (spec 34) run the SAME engine over the SAME
// workspace deal, so the shared verdict can never disagree with itself.
export function dealReadinessSnapshot() {
  return dealReadiness({
    reels: [trustScore(DEAL.reelEvidence)],
    fieldCase: DEAL.fieldCase,
    compliance: DEAL.compliance,
    diligence: DEAL.diligence,
    terms: DEAL.terms
  })
}

export function deriveWorkspaceAlerts(now = Date.now()) {
  const flagship = TENANTS[0]
  return deriveAlerts({
    sla: slaSummary(ticketsAt(now), now),
    health: healthSummary(ACCOUNTS),
    compliance: assessCampaign(CAMPAIGN),
    invoice: invoice(PLAN_BASE_FEES[flagship.plan], METERS[flagship.id]),
    readiness: dealReadinessSnapshot()
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
  prefs.recents = fresh.recents
  prefs.motion = fresh.motion
  prefs.consent = fresh.consent
}
