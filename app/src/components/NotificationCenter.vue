<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { deriveAlerts, createInbox } from '../logic/notifications.js'
import { slaSummary, healthSummary } from '../logic/customerSuccess.js'
import { assessCampaign } from '../logic/riskLegal.js'
import { invoice } from '../logic/metering.js'
import { dealReadiness } from '../logic/pipeline.js'
import { trustScore } from '../logic/showcase.js'

const { t } = useI18n()
const router = useRouter()

// Demo inputs run through the REAL engines — the bell reflects the truth
// of the workspace's demo data, not hand-written alerts (spec 26).
const now = Date.now()
const hrs = n => new Date(now + n * 3600000).toISOString()

const inputs = {
  sla: slaSummary([
    { due: hrs(-0.5), sla: 1, status: 'active', csat: null },
    { due: hrs(-2), sla: 8, status: 'active', csat: null },
    { due: hrs(4), sla: 8, status: 'active', csat: null }
  ], now),
  health: healthSummary([
    { name: 'Mizu Logistics', mrr: 980, signals: { usage: 38, payment: 68, support: 52, adoption: 34, sentiment: 42 }, renewalIn: 42 },
    { name: 'Lumen Studios', mrr: 9800, signals: { usage: 92, payment: 100, support: 88, adoption: 84, sentiment: 92 }, renewalIn: 172 }
  ]),
  compliance: assessCampaign({ markets: ['JP', 'EU'], attributes: { consent: true, dpa: true, localization: true, adDisclosure: true, provenance: true } }),
  invoice: invoice(5000, [{ used: 12480, included: 10000, cost: 2246 }]),
  readiness: dealReadiness({
    reels: [trustScore({ provenance: true, complianceGate: true })],
    fieldCase: { state: 'evidence-collected', chainValid: true },
    compliance: { gate: 'pass' }, diligence: { gate: 'pass' }, terms: { verdict: 'counter' }
  })
}

const inbox = createInbox()
for (const a of deriveAlerts(inputs)) inbox.push(a, now)

const open = ref(false)
const version = ref(0)
const items = computed(() => { void version.value; return inbox.list() })
const unread = computed(() => { void version.value; return inbox.unreadCount() })

const DOT = { critical: '#f87171', warning: '#fbbf24', info: '#22d3ee' }

function go(item) {
  inbox.markRead(item.key)
  version.value++
  open.value = false
  router.push(item.route)
}
function markAll() { inbox.markAllRead(); version.value++ }
</script>

<template>
  <div class="nc">
    <button class="bell" type="button" @click="open = !open" :title="t('notify.title')">
      🔔<span v-if="unread" class="badge">{{ unread }}</span>
    </button>

    <div v-if="open" class="panel card">
      <div class="p-head">
        <strong>{{ t('notify.title') }}</strong>
        <button v-if="unread" class="mark" type="button" @click="markAll">{{ t('notify.markAll') }}</button>
      </div>
      <div v-if="!items.length" class="empty">{{ t('notify.empty') }}</div>
      <button v-for="i in items" :key="i.key" type="button" class="row" :class="{ read: i.read }" @click="go(i)">
        <span class="dot" :style="{ background: DOT[i.severity] }"></span>
        <span class="msg">{{ t(i.msgKey, i.params) }}</span>
        <span class="go">→</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.nc { position: relative; }
.bell { position: relative; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface); cursor: pointer; font-size: 15px; }
.bell:hover { border-color: rgba(124, 92, 255, .5); }
.badge { position: absolute; top: -6px; right: -6px; min-width: 18px; height: 18px; border-radius: 999px; background: #f87171; color: #fff; font-size: 10px; font-weight: 800; display: grid; place-items: center; padding: 0 4px; }

.panel { position: absolute; right: 0; top: 44px; width: min(400px, 88vw); z-index: 50; padding: 12px; }
.p-head { display: flex; justify-content: space-between; align-items: center; padding: 2px 4px 10px; font-size: 13px; }
.mark { border: 0; background: transparent; color: var(--primary); font-size: 11px; cursor: pointer; }
.empty { padding: 16px 4px; font-size: 12px; color: var(--text-dim); text-align: center; }
.row { display: grid; grid-template-columns: 10px 1fr auto; gap: 10px; align-items: center; width: 100%; text-align: left; padding: 10px 8px; border: 0; border-radius: 8px; background: transparent; color: var(--text); font-size: 12.5px; cursor: pointer; line-height: 1.45; }
.row:hover { background: rgba(124, 92, 255, .1); }
.row.read { opacity: .55; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.go { color: var(--text-dim); font-size: 12px; }
</style>
