<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { upcomingMoments, atRisk, STAGES, leadTimeDays } from '../logic/retailMoments.js'

const { t, locale } = useI18n()

const DAY = 86400000
// Deterministic clock — a planning surface must render the same thing twice.
const NOW = Date.UTC(2026, 8, 1)

const MOMENTS = [
  { key: 'fiestas', market: 'MX', at: Date.UTC(2026, 8, 16) },
  { key: 'oktoberfest', market: 'DE', at: Date.UTC(2026, 8, 19) },
  { key: 'ramadan', market: 'AE', at: Date.UTC(2027, 1, 17) },
  { key: 'singles', market: 'ID', at: Date.UTC(2026, 10, 11) },
  { key: 'bfcm', market: 'DE', at: Date.UTC(2026, 10, 27) },
  { key: 'buenfin', market: 'MX', at: Date.UTC(2026, 10, 13) },
  { key: 'oshogatsu', market: 'JP', at: Date.UTC(2027, 0, 1) },
  { key: 'blackfridayBr', market: 'BR', at: Date.UTC(2026, 10, 27) },
  { key: 'goldenweek', market: 'JP', at: Date.UTC(2027, 3, 29) },
  { key: 'harbolnas', market: 'ID', at: Date.UTC(2026, 11, 12) }
]

const horizon = ref(240)
const moments = computed(() => upcomingMoments(MOMENTS, NOW, { horizonDays: horizon.value }))
const risky = computed(() => atRisk(MOMENTS, NOW, { horizonDays: horizon.value }))
const lead = leadTimeDays()

const selected = ref(null)
const focus = computed(() => moments.value.find(m => m.key === selected.value) ?? moments.value[0] ?? null)

const dateFmt = ts => new Intl.DateTimeFormat(locale.value, { month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(ts))
const longFmt = ts => new Intl.DateTimeFormat(locale.value, { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' }).format(new Date(ts))

// Bar geometry across the visible window, so a stage's width is its duration.
const span = computed(() => Math.max(1, horizon.value))
const pos = ts => Math.max(0, Math.min(100, ((ts - NOW) / DAY / span.value) * 100))
</script>

<template>
  <div class="rc">
    <div class="card head">
      <div>
        <div class="kicker">{{ t('moments.kicker') }}</div>
        <h3>{{ t('moments.title') }}</h3>
        <p class="meta">{{ t('moments.sub', { days: lead }) }}</p>
      </div>
      <div class="tot">
        <div class="tn" :class="risky.length ? 'risk' : 'grad-text'">{{ risky.length }}</div>
        <div class="tl">{{ t('moments.lateNow') }}</div>
      </div>
    </div>

    <div v-if="risky.length" class="card alert">
      <span class="ai-tag">{{ t('moments.act') }}</span>
      <span>{{ t('moments.alert', {
        list: risky.map(m => t(`moments.m.${m.key}`)).join(', '),
        days: Math.abs(risky[0].plan.slackDays)
      }) }}</span>
    </div>

    <div class="card">
      <div class="th-row">
        <h3>{{ t('moments.window') }}</h3>
        <label class="hz">{{ t('moments.horizon') }}
          <select v-model.number="horizon" :aria-label="t('moments.horizon')">
            <option :value="120">120</option>
            <option :value="240">240</option>
            <option :value="365">365</option>
          </select>
        </label>
      </div>

      <p v-if="!moments.length" class="empty">{{ t('moments.none') }}</p>
      <div v-for="m in moments" :key="m.key" class="mrow" :class="m.plan.status">
        <button type="button" class="mlabel" :aria-pressed="m.key === focus?.key" @click="selected = m.key">
          <span class="mname">{{ t(`moments.m.${m.key}`) }}</span>
          <span class="mmk">{{ t(`market.${m.market}`) }} · {{ dateFmt(m.at) }}</span>
        </button>
        <div class="track" :aria-label="t('moments.trackFor', { moment: t(`moments.m.${m.key}`) })">
          <div class="run" :class="m.plan.status"
            :style="{ left: pos(m.plan.startBy) + '%', width: Math.max(1.5, pos(m.at) - pos(m.plan.startBy)) + '%' }"></div>
          <div class="pin" :style="{ left: pos(m.at) + '%' }"></div>
        </div>
        <span class="slack" :class="m.plan.status">
          {{ m.plan.slackDays < 0
            ? t('moments.lateBy', { n: Math.abs(m.plan.slackDays) })
            : t('moments.startIn', { n: m.plan.slackDays }) }}
        </span>
      </div>
      <p class="foot">{{ t('moments.backwardNote') }}</p>
    </div>

    <div class="card plan" v-if="focus">
      <div class="kicker">{{ t('moments.plan') }}</div>
      <h3>{{ t(`moments.m.${focus.key}`) }} · {{ longFmt(focus.at) }}</h3>
      <p class="meta">{{ t('moments.startBy', { date: longFmt(focus.plan.startBy), days: focus.plan.leadDays }) }}</p>
      <ol class="stages">
        <li v-for="s in focus.plan.stages" :key="s.key" :class="{ late: s.late }">
          <span class="s-k">{{ t(`moments.stage.${s.key}`) }}</span>
          <span class="s-d">{{ dateFmt(s.start) }} → {{ dateFmt(s.end) }}</span>
          <span class="s-n">{{ t('moments.days', { n: s.days }) }}</span>
          <span v-if="s.late" class="s-late">{{ t('moments.overdue') }}</span>
        </li>
      </ol>
      <p class="foot">{{ t('moments.stagesNote', { list: STAGES.map(s => t(`moments.stage.${s.key}`)).join(' → ') }) }}</p>
    </div>
  </div>
</template>

<style scoped>
.rc { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.tot { text-align: right; }
.tn { font-size: 26px; font-weight: 800; line-height: 1; }
.tn.risk { color: var(--danger); }
.tl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.card { padding: 18px 20px; }
.alert { display: flex; gap: 10px; align-items: flex-start; font-size: 12px; color: var(--text-dim); line-height: 1.55;
  border-color: rgba(248, 113, 113, .3); background: rgba(248, 113, 113, .07); }
.ai-tag { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; font-size: 9px;
  padding: 2px 6px; border-radius: 4px; font-weight: 800; letter-spacing: .05em; flex-shrink: 0; }

.th-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.hz { font-size: 12px; color: var(--text-dim); display: inline-flex; align-items: center; gap: 8px; }
.hz select { background: var(--surface); border: 1px solid var(--border); color: var(--text);
  border-radius: 8px; padding: 5px 9px; font-size: 12px; }
.hz select:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.empty { font-size: 12px; color: var(--text-dim); }

.mrow { display: grid; grid-template-columns: 168px 1fr 92px; gap: 12px; align-items: center;
  padding: 8px 0; border-bottom: 1px dashed var(--border); }
.mlabel { background: transparent; border: 0; padding: 2px 4px; text-align: left; cursor: pointer; color: var(--text); border-radius: 6px; }
.mlabel:hover { background: var(--surface); }
.mlabel:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.mname { display: block; font-size: 12px; font-weight: 600; }
.mmk { display: block; font-size: 10px; color: var(--text-dim); margin-top: 1px; }
.track { position: relative; height: 16px; background: var(--bg-2); border-radius: 8px; }
.run { position: absolute; top: 4px; height: 8px; border-radius: 4px;
  background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.run.late { background: linear-gradient(90deg, #f87171, #fcd34d); }
.pin { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--text); border-radius: 1px; }
.slack { font-size: 11px; text-align: right; font-variant-numeric: tabular-nums; color: var(--text-dim); }
.slack.late { color: #fca5a5; font-weight: 700; }
.foot { font-size: 11px; color: var(--text-dim); margin: 14px 0 0; line-height: 1.55; }

.stages { list-style: none; margin: 12px 0 0; padding: 0; counter-reset: st; }
.stages li { display: grid; grid-template-columns: 1fr auto auto auto; gap: 10px; align-items: baseline;
  padding: 8px 0; border-bottom: 1px dashed var(--border); font-size: 12px; }
.stages li.late .s-k { color: #fca5a5; }
.s-d { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.s-n { font-size: 11px; color: var(--text-dim); }
.s-late { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em;
  padding: 1px 6px; border-radius: 4px; background: rgba(248, 113, 113, .16); color: #fca5a5; }

@media (max-width: 900px) { .mrow { grid-template-columns: 120px 1fr 78px; } }
</style>
