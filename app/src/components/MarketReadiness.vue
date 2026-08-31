<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { readinessRank, readiness, GATE_KINDS } from '../logic/goLive.js'

const { t, locale } = useI18n()

const B = GATE_KINDS.blocking
const A = GATE_KINDS.advisory
const g = (key, kind, status, etaDays = 0, weight = 1, owner = 'ops') => ({ key, kind, status, etaDays, weight, owner })

const MARKETS = [
  { code: 'JP', flag: '🇯🇵', gates: [
    g('entity', B, 'done'), g('tax', B, 'done'), g('dataResidency', B, 'done'),
    g('paymentRail', A, 'done', 0, 3, 'finance'), g('supportHours', A, 'open', 12, 2, 'cx'),
    g('localeQa', A, 'done', 0, 2, 'loc'), g('legalPages', A, 'done', 0, 1, 'legal') ] },
  { code: 'DE', flag: '🇩🇪', gates: [
    g('entity', B, 'done'), g('tax', B, 'open', 34, 1, 'finance'), g('dataResidency', B, 'done'),
    g('paymentRail', A, 'done', 0, 3, 'finance'), g('supportHours', A, 'done', 0, 2, 'cx'),
    g('localeQa', A, 'done', 0, 2, 'loc'), g('legalPages', A, 'open', 9, 1, 'legal') ] },
  { code: 'AE', flag: '🇦🇪', gates: [
    g('entity', B, 'done'), g('tax', B, 'done'), g('dataResidency', B, 'done'),
    g('paymentRail', A, 'open', 18, 3, 'finance'), g('supportHours', A, 'open', 6, 2, 'cx'),
    g('localeQa', A, 'open', 21, 2, 'loc'), g('legalPages', A, 'done', 0, 1, 'legal') ] },
  { code: 'BR', flag: '🇧🇷', gates: [
    g('entity', B, 'open', 75, 1, 'legal'), g('tax', B, 'open', 60, 1, 'finance'), g('dataResidency', B, 'open', 40, 1, 'sec'),
    g('paymentRail', A, 'open', 25, 3, 'finance'), g('supportHours', A, 'open', 30, 2, 'cx'),
    g('localeQa', A, 'done', 0, 2, 'loc'), g('legalPages', A, 'open', 15, 1, 'legal') ] },
  { code: 'ID', flag: '🇮🇩', gates: [
    g('entity', B, 'done'), g('tax', B, 'open', 45, 1, 'finance'), g('dataResidency', B, 'open', 52, 1, 'sec'),
    g('paymentRail', A, 'open', 20, 3, 'finance'), g('supportHours', A, 'open', 14, 2, 'cx'),
    g('localeQa', A, 'open', 28, 2, 'loc'), g('legalPages', A, 'open', 10, 1, 'legal') ] },
  { code: 'MX', flag: '🇲🇽', gates: [
    g('entity', B, 'done'), g('tax', B, 'done'), g('dataResidency', B, 'done'),
    g('paymentRail', A, 'open', 8, 3, 'finance'), g('supportHours', A, 'done', 0, 2, 'cx'),
    g('localeQa', A, 'open', 16, 2, 'loc'), g('legalPages', A, 'done', 0, 1, 'legal') ] }
]

// Deterministic clock: the panel is a planning surface, not a live ticker, and
// a fixture that shifts with the wall clock cannot be reasoned about or tested.
const NOW = Date.UTC(2026, 8, 1)

const ranked = computed(() => readinessRank(MARKETS, NOW)
  .map(r => ({ ...r, flag: MARKETS.find(m => m.code === r.code).flag })))
const live = computed(() => ranked.value.filter(r => r.canGoLive))

const selected = ref(null)
const current = computed(() => MARKETS.find(m => m.code === (selected.value ?? ranked.value[0]?.code)))
const detail = computed(() => current.value ? readiness(current.value.gates, NOW) : null)

const dateFmt = ts => new Intl.DateTimeFormat(locale.value, { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(ts))
</script>

<template>
  <div class="mr">
    <div class="card head">
      <div>
        <div class="kicker">{{ t('golive.kicker') }}</div>
        <h3>{{ t('golive.title') }}</h3>
        <p class="meta">{{ t('golive.sub') }}</p>
      </div>
      <div class="tot">
        <div class="tn grad-text">{{ live.length }}/{{ ranked.length }}</div>
        <div class="tl">{{ t('golive.canTransact') }}</div>
      </div>
    </div>

    <div class="row">
      <div class="card list">
        <h3>{{ t('golive.byReadiness') }}</h3>
        <button v-for="m in ranked" :key="m.code" type="button" class="mk"
          :class="{ on: m.code === current?.code, blocked: !m.canGoLive }"
          :aria-pressed="m.code === current?.code" @click="selected = m.code">
          <span class="flag" aria-hidden="true">{{ m.flag }}</span>
          <span class="mk-main">
            <span class="mk-name">{{ t(`market.${m.code}`) }}</span>
            <span class="mk-sub">
              <template v-if="m.canGoLive">{{ t('golive.clear', { pct: m.advisoryPct.toFixed(0) }) }}</template>
              <template v-else>{{ t('golive.blockedBy', { list: m.blockers.map(b => t(`golive.gate.${b}`)).join(', ') }) }}</template>
            </span>
          </span>
          <span class="mk-eta">
            <span class="days">{{ m.criticalPathDays }}<small>{{ t('golive.d') }}</small></span>
            <span class="pill" :class="m.canGoLive ? 'ok' : 'block'">{{ m.canGoLive ? t('golive.live') : t('golive.held') }}</span>
          </span>
        </button>
      </div>

      <div class="card detail" v-if="current && detail">
        <div class="kicker">{{ t('golive.gates') }}</div>
        <h3>{{ current.flag }} {{ t(`market.${current.code}`) }}</h3>
        <p class="meta">
          {{ detail.canGoLive
            ? t('golive.readyNote', { date: dateFmt(detail.earliestGoLive) })
            : t('golive.heldNote', { n: detail.blockers.length, date: dateFmt(detail.earliestGoLive) }) }}
        </p>

        <div class="meters">
          <div class="m">
            <span class="m-l">{{ t('golive.blockingGates') }}</span>
            <span class="m-bar"><i :class="detail.canGoLive ? 'ok' : 'block'" :style="{ width: detail.blockingPct + '%' }"></i></span>
            <span class="m-v">{{ detail.blockingPct.toFixed(0) }}%</span>
          </div>
          <div class="m">
            <span class="m-l">{{ t('golive.advisoryGates') }}</span>
            <span class="m-bar"><i class="adv" :style="{ width: detail.advisoryPct + '%' }"></i></span>
            <span class="m-v">{{ detail.advisoryPct.toFixed(0) }}%</span>
          </div>
        </div>
        <p class="sep-note">{{ t('golive.whySeparate') }}</p>

        <ul class="gates">
          <li v-for="gate in current.gates" :key="gate.key" :class="[gate.kind, gate.status]">
            <span class="g-ico" aria-hidden="true">{{ gate.status === 'done' ? '✓' : gate.kind === 'blocking' ? '✕' : '○' }}</span>
            <span class="g-name">
              {{ t(`golive.gate.${gate.key}`) }}
              <span class="g-kind">{{ t(`golive.kind.${gate.kind}`) }}</span>
            </span>
            <span class="g-eta">{{ gate.status === 'done' ? t('golive.done') : t('golive.inDays', { n: gate.etaDays, owner: t(`golive.owner.${gate.owner}`) }) }}</span>
          </li>
        </ul>

        <div class="cp" v-if="detail.openCount">
          {{ t('golive.criticalPath', {
            days: detail.criticalPathDays,
            owner: detail.owner ? t(`golive.owner.${detail.owner}`) : '—',
            date: dateFmt(detail.earliestGoLive)
          }) }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mr { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.tot { text-align: right; }
.tn { font-size: 26px; font-weight: 800; line-height: 1; }
.tl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.row { display: grid; grid-template-columns: 1fr 1.15fr; gap: 16px; align-items: start; }
.list, .detail { padding: 18px 20px; }

.mk { display: grid; grid-template-columns: 26px 1fr auto; gap: 10px; align-items: center; width: 100%;
  background: transparent; border: 1px solid transparent; border-bottom: 1px dashed var(--border);
  padding: 10px 8px; cursor: pointer; color: var(--text); text-align: left; border-radius: 8px; margin-top: 4px; }
.mk:hover { background: var(--surface); }
.mk.on { border-color: var(--primary); background: var(--surface); }
.mk:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.mk.blocked .mk-name { color: #fca5a5; }
.flag { font-size: 18px; }
.mk-name { display: block; font-size: 13px; font-weight: 600; }
.mk-sub { display: block; font-size: 11px; color: var(--text-dim); margin-top: 2px; }
.mk-eta { text-align: right; }
.days { display: block; font-size: 16px; font-weight: 800; font-variant-numeric: tabular-nums; }
.days small { font-size: 10px; font-weight: 600; color: var(--text-dim); margin-left: 1px; }
.pill { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; padding: 1px 6px; border-radius: 4px; }
.pill.ok { background: rgba(52, 211, 153, .16); color: #6ee7b7; }
.pill.block { background: rgba(248, 113, 113, .16); color: #fca5a5; }

.meters { display: flex; flex-direction: column; gap: 8px; margin: 14px 0 8px; }
.m { display: grid; grid-template-columns: 110px 1fr 44px; gap: 10px; align-items: center; font-size: 11px; color: var(--text-dim); }
.m-bar { height: 7px; background: var(--bg-2); border-radius: 4px; overflow: hidden; }
.m-bar i { display: block; height: 100%; }
.m-bar i.ok { background: var(--success); }
.m-bar i.block { background: var(--danger); }
.m-bar i.adv { background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.m-v { text-align: right; font-variant-numeric: tabular-nums; color: var(--text); }
.sep-note { font-size: 11px; color: var(--text-dim); margin: 0 0 12px; line-height: 1.55; }

.gates { list-style: none; margin: 0; padding: 12px 0 0; border-top: 1px solid var(--border); }
.gates li { display: grid; grid-template-columns: 20px 1fr auto; gap: 8px; align-items: baseline;
  padding: 7px 0; border-bottom: 1px dashed var(--border); font-size: 12px; }
.g-ico { font-weight: 800; }
.gates li.done .g-ico { color: var(--success); }
.gates li.blocking.open .g-ico { color: var(--danger); }
.gates li.advisory.open .g-ico { color: var(--text-dim); }
.g-kind { font-size: 9px; text-transform: uppercase; letter-spacing: .06em; padding: 1px 5px; border-radius: 4px;
  background: var(--bg-2); color: var(--text-dim); margin-left: 6px; }
.gates li.blocking .g-kind { background: rgba(248, 113, 113, .14); color: #fca5a5; }
.g-eta { font-size: 11px; color: var(--text-dim); text-align: right; }

.cp { margin-top: 14px; padding: 11px 13px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--surface); font-size: 12px; color: var(--text-dim); line-height: 1.55; }

@media (max-width: 1024px) { .row { grid-template-columns: 1fr; } }
</style>
