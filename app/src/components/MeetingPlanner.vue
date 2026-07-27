<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { zoneOffsetMinutes, localHour, overlapHours, suggestSlot } from '../logic/timezones.js'

// Spec 36 — find the working-hours overlap for a cross-border call, the way
// World Time Buddy / Calendly do. Real IANA zones, DST-correct at `now`.
const { t } = useI18n()

const ZONES = [
  { id: 'Asia/Shanghai', city: 'Shanghai' },
  { id: 'Asia/Tokyo', city: 'Tokyo' },
  { id: 'Asia/Singapore', city: 'Singapore' },
  { id: 'Asia/Kolkata', city: 'Mumbai' },
  { id: 'Europe/Berlin', city: 'Berlin' },
  { id: 'Europe/London', city: 'London' },
  { id: 'America/Sao_Paulo', city: 'São Paulo' },
  { id: 'America/New_York', city: 'New York' },
  { id: 'America/Los_Angeles', city: 'Los Angeles' }
]

const now = Date.now() // frozen per view so the plan is stable
const host = ref('Asia/Shanghai')
const partner = ref('America/New_York')

const offHost = computed(() => zoneOffsetMinutes(host.value, now))
const offPartner = computed(() => zoneOffsetMinutes(partner.value, now))
const hours = computed(() => overlapHours(offHost.value, offPartner.value))
const slot = computed(() => suggestSlot(hours.value))
const overlapSet = computed(() => new Set(hours.value))

function cityOf(id) { return ZONES.find(z => z.id === id)?.city ?? id }
function fmtHour(h) {
  const hh = Math.floor(h)
  const mm = h % 1 ? '30' : '00'
  return `${String(hh).padStart(2, '0')}:${mm}`
}

const strip = computed(() =>
  Array.from({ length: 24 }, (_, u) => ({
    u,
    host: fmtHour(localHour(u, offHost.value)),
    partner: fmtHour(localHour(u, offPartner.value)),
    on: overlapSet.value.has(u)
  }))
)
</script>

<template>
  <div class="mp">
    <div class="card head">
      <div>
        <div class="kicker">{{ t('planner.kicker') }}</div>
        <h3>{{ t('planner.title') }}</h3>
        <p class="meta">{{ t('planner.sub') }}</p>
      </div>
    </div>

    <div class="card pick">
      <label class="pk">
        <span class="kicker">{{ t('planner.host') }}</span>
        <select v-model="host" :aria-label="t('planner.host')">
          <option v-for="z in ZONES" :key="z.id" :value="z.id">{{ z.city }}</option>
        </select>
      </label>
      <label class="pk">
        <span class="kicker">{{ t('planner.partner') }}</span>
        <select v-model="partner" :aria-label="t('planner.partner')">
          <option v-for="z in ZONES" :key="z.id" :value="z.id">{{ z.city }}</option>
        </select>
      </label>
    </div>

    <div class="card result" :class="{ none: slot === null }">
      <template v-if="slot !== null">
        <div class="rs-lead">{{ t('planner.overlap', { n: hours.length }) }}</div>
        <div class="rs-slot">
          <span class="rs-lbl">{{ t('planner.suggest') }}</span>
          <span class="rs-pair">
            <strong>{{ cityOf(host) }}</strong> {{ fmtHour(localHour(slot, offHost)) }}
            <span class="rs-arrow" aria-hidden="true">↔</span>
            <strong>{{ cityOf(partner) }}</strong> {{ fmtHour(localHour(slot, offPartner)) }}
          </span>
        </div>
      </template>
      <div v-else class="rs-none">{{ t('planner.none') }}</div>
    </div>

    <div class="card">
      <div class="lg">{{ t('planner.working') }}</div>
      <div class="strip" role="list" :aria-label="t('planner.title')">
        <div v-for="c in strip" :key="c.u" class="col" :class="{ on: c.on }" role="listitem"
             :title="`UTC ${String(c.u).padStart(2,'0')}:00 · ${cityOf(host)} ${c.host} · ${cityOf(partner)} ${c.partner}`">
          <span class="c-host">{{ c.host }}</span>
          <span class="c-bar"></span>
          <span class="c-part">{{ c.partner }}</span>
        </div>
      </div>
      <div class="axis"><span>{{ cityOf(host) }}</span><span>{{ cityOf(partner) }}</span></div>
    </div>
  </div>
</template>

<style scoped>
.mp { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; font-weight: 700; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.pick { display: flex; gap: 24px; padding: 16px 20px; flex-wrap: wrap; }
.pk { display: flex; flex-direction: column; gap: 6px; }
.pk select { background: var(--surface); border: 1px solid var(--border); color: var(--text); border-radius: 9px; padding: 9px 12px; font-size: 14px; min-width: 180px; }
.pk select:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

.result { padding: 18px 20px; border-left: 4px solid var(--success); }
.result.none { border-left-color: var(--danger); }
.rs-lead { font-size: 13px; color: var(--text-dim); }
.rs-slot { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin-top: 8px; }
.rs-lbl { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: var(--text-dim); }
.rs-pair { font-size: 20px; font-variant-numeric: tabular-nums; }
.rs-arrow { margin: 0 8px; color: var(--text-dim); }
.rs-none { font-size: 14px; }

.lg { font-size: 11px; color: var(--text-dim); margin-bottom: 10px; }
.strip { display: grid; grid-template-columns: repeat(24, 1fr); gap: 2px; }
.col { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px 0; border-radius: 5px; background: var(--surface); }
.col.on { background: rgba(52, 211, 153, .18); outline: 1px solid rgba(52, 211, 153, .5); }
.c-host, .c-part { font-size: 8px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.col.on .c-host, .col.on .c-part { color: var(--text); }
.c-bar { width: 100%; height: 3px; border-radius: 2px; background: var(--border); }
.col.on .c-bar { background: var(--success); }
.axis { display: flex; justify-content: space-between; font-size: 10px; color: var(--text-dim); margin-top: 8px; }

@media (max-width: 640px) {
  .c-host, .c-part { font-size: 0; }
  .c-host::before { content: '·'; font-size: 10px; }
  .c-part { display: none; }
}
</style>
