<script setup>
import { ref, computed } from 'vue'

const contracts = ref([
  { id: 'C-204', name: 'Lumen Studios',       tcv: 840000, start: 0, term: 12, obligations: [
    { name: 'Platform · sub',    amount: 720000, kind: 'ratable',    start: 0,  end: 12 },
    { name: 'Onboarding',        amount:  60000, kind: 'point-in-time', start: 0, end: 1 },
    { name: 'Training',          amount:  32000, kind: 'point-in-time', start: 1, end: 2 },
    { name: 'GPU commit rebate', amount:  28000, kind: 'ratable',      start: 0, end: 12 }
  ]},
  { id: 'C-198', name: 'Northwave Partners',  tcv: 1200000, start: 0, term: 24, obligations: [
    { name: 'Platform · sub',    amount: 960000, kind: 'ratable', start: 0, end: 24 },
    { name: 'Prof services',     amount: 240000, kind: 'milestone', start: 0, end: 6 }
  ]},
  { id: 'C-191', name: 'Cobalt Legal',        tcv: 220000, start: 0, term: 12, obligations: [
    { name: 'Platform · sub',    amount: 200000, kind: 'ratable',    start: 0, end: 12 },
    { name: 'Onboarding',        amount:  20000, kind: 'point-in-time', start: 0, end: 1 }
  ]}
])

const selected = ref('C-204')
const cur = computed(() => contracts.value.find(c => c.id === selected.value))
const months = 12

// Build monthly schedule for current contract
const schedule = computed(() => {
  const arr = Array.from({ length: months }, (_, i) => ({ month: i + 1, obligations: {} }))
  for (const o of cur.value.obligations) {
    for (let m = 0; m < months; m++) {
      let val = 0
      if (o.kind === 'ratable') {
        if (m >= o.start && m < o.end) val = o.amount / (o.end - o.start)
      } else if (o.kind === 'point-in-time') {
        if (m === o.start) val = o.amount
      } else if (o.kind === 'milestone') {
        // Split into 3 equal milestones
        const step = (o.end - o.start) / 3
        for (let i = 0; i < 3; i++) {
          if (Math.floor(o.start + step * i) === m) val += o.amount / 3
        }
      }
      arr[m].obligations[o.name] = val
    }
  }
  return arr
})

const monthlyTotals = computed(() => schedule.value.map(row => Object.values(row.obligations).reduce((s, v) => s + v, 0)))
const monthlyMax = computed(() => Math.max(...monthlyTotals.value))
const totalRecognized = computed(() => monthlyTotals.value.reduce((s, v) => s + v, 0))
const totalDeferred = computed(() => cur.value.tcv - totalRecognized.value)

const cumulative = computed(() => {
  let acc = 0
  return monthlyTotals.value.map(v => (acc += v))
})

const colors = { 'Platform · sub': '#7c5cff', 'Onboarding': '#22d3ee', 'Training': '#ff7ad9', 'GPU commit rebate': '#34d399', 'Prof services': '#fcd34d' }

const summary = computed(() => ({
  totalTCV: contracts.value.reduce((s, c) => s + c.tcv, 0),
  totalARR: contracts.value.reduce((s, c) => {
    return s + c.obligations.filter(o => o.kind === 'ratable').reduce((sum, o) => sum + o.amount / (o.end - o.start) * 12, 0)
  }, 0),
  totalDeferred: contracts.value.reduce((s, c) => s + c.tcv, 0) - contracts.value.reduce((s, c) => s + c.obligations.filter(o => o.kind === 'point-in-time' && o.start === 0).reduce((sum, o) => sum + o.amount, 0), 0),
  count: contracts.value.length
}))
</script>

<template>
  <div class="rr">
    <div class="card head">
      <div>
        <div class="kicker">Revenue recognition · ASC 606</div>
        <h3>Deferred → recognized schedule</h3>
        <p class="meta">Each contract split into performance obligations. Ratable rev recognized monthly; point-in-time at delivery; milestones at completion.</p>
      </div>
      <div class="kpis">
        <div><div class="kn grad-text">${{ (summary.totalTCV / 1e6).toFixed(2) }}M</div><div class="kl">TCV</div></div>
        <div><div class="kn">${{ (summary.totalARR / 1e6).toFixed(2) }}M</div><div class="kl">ARR contracted</div></div>
        <div><div class="kn">${{ Math.round(summary.totalDeferred / 1000) }}k</div><div class="kl">Deferred balance</div></div>
      </div>
    </div>

    <div class="c-pick">
      <button v-for="c in contracts" :key="c.id" :class="{ on: selected === c.id }" @click="selected = c.id" type="button">
        <span class="c-id">{{ c.id }}</span>
        <span class="c-name">{{ c.name }}</span>
        <span class="c-tcv">${{ Math.round(c.tcv / 1000) }}k · {{ c.term }}mo</span>
      </button>
    </div>

    <div class="card">
      <div class="hh">
        <h3>{{ cur.name }} · {{ months }}-month schedule</h3>
        <span class="meta">${{ Math.round(cur.tcv / 1000) }}k TCV → ${{ Math.round(totalRecognized / 1000) }}k recognized · ${{ Math.round(totalDeferred / 1000) }}k deferred</span>
      </div>

      <div class="chart">
        <div v-for="(row, i) in schedule" :key="i" class="col">
          <div class="col-stack">
            <div v-for="(v, k) in row.obligations" :key="k" class="seg"
              :style="{ height: (v / monthlyMax * 100) + '%', background: colors[k] || '#94a3b8' }"
              :title="`${k}: $${Math.round(v).toLocaleString()}`"></div>
          </div>
          <div class="col-num">${{ Math.round(monthlyTotals[i] / 1000) }}k</div>
          <div class="col-lbl">M{{ row.month }}</div>
        </div>
      </div>

      <div class="legend">
        <span v-for="o in cur.obligations" :key="o.name">
          <span class="lg" :style="{ background: colors[o.name] || '#94a3b8' }"></span>
          {{ o.name }} · <span class="dimc-i">{{ o.kind }}</span>
        </span>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>Performance obligations</h3>
        <table class="po">
          <thead>
            <tr>
              <th>Obligation</th>
              <th class="num">Amount</th>
              <th>Recognition</th>
              <th>Window</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="o in cur.obligations" :key="o.name">
              <td><span class="po-dot" :style="{ background: colors[o.name] || '#94a3b8' }"></span>{{ o.name }}</td>
              <td class="num">${{ o.amount.toLocaleString() }}</td>
              <td><span class="kind" :class="o.kind">{{ o.kind }}</span></td>
              <td class="dimc">M{{ o.start + 1 }} → M{{ o.end }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>Deferred vs recognized · cumulative</h3>
        <p class="meta">Deferred balance drains as revenue is recognized month-by-month.</p>
        <svg viewBox="0 0 380 140" class="cc" preserveAspectRatio="none">
          <g stroke="var(--border)" stroke-dasharray="3 3" stroke-width="1">
            <line x1="0" y1="130" x2="380" y2="130" />
            <line x1="0" y1="70" x2="380" y2="70" />
          </g>
          <path :d="`M0,130 ${cumulative.map((v, i) => `L${((i + 1) / months) * 380},${130 - (v / cur.tcv) * 120}`).join(' ')} L380,130 Z`"
            fill="url(#rgg)" stroke="none" opacity=".35" />
          <path :d="`M0,130 ${cumulative.map((v, i) => `L${((i + 1) / months) * 380},${130 - (v / cur.tcv) * 120}`).join(' ')}`"
            fill="none" stroke="url(#rgg)" stroke-width="2.5" stroke-linecap="round" />
          <defs>
            <linearGradient id="rgg" x1="0" x2="1">
              <stop offset="0" stop-color="#7c5cff" />
              <stop offset="1" stop-color="#22d3ee" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rr { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.dimc-i { color: var(--text-dim); font-size: 11px; }
.dimc { color: var(--text-dim); }

.kpis { display: flex; gap: 20px; }
.kn { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.kl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.c-pick { display: flex; gap: 8px; flex-wrap: wrap; }
.c-pick button { padding: 12px 16px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); color: var(--text); cursor: pointer; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; text-align: left; }
.c-pick button:hover { border-color: var(--primary); }
.c-pick button.on { border-color: var(--primary); background: rgba(124, 92, 255, .1); }
.c-id { font-family: ui-monospace, monospace; font-size: 10px; color: var(--primary-2); font-weight: 700; }
.c-name { font-weight: 700; font-size: 14px; }
.c-tcv { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; }

.hh { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; flex-wrap: wrap; gap: 12px; }

.chart { display: grid; grid-template-columns: repeat(12, 1fr); gap: 6px; height: 220px; align-items: end; margin: 10px 0 14px; }
.col { display: flex; flex-direction: column; align-items: center; height: 100%; }
.col-stack { flex: 1; width: 100%; display: flex; flex-direction: column-reverse; border-radius: 5px 5px 0 0; overflow: hidden; }
.seg { width: 100%; min-height: 1px; transition: opacity .15s; }
.seg:hover { opacity: .7; cursor: pointer; }
.col-num { font-size: 10px; font-variant-numeric: tabular-nums; color: var(--text); margin-top: 6px; }
.col-lbl { font-size: 10px; color: var(--text-dim); }

.legend { display: flex; flex-wrap: wrap; gap: 16px; padding-top: 14px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text); }
.lg { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }

.row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.po { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 12px; }
.po th { text-align: left; padding: 8px 10px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.po th.num { text-align: right; }
.po td { padding: 12px 10px; border-bottom: 1px dashed var(--border); }
.po td.num { text-align: right; font-variant-numeric: tabular-nums; }
.po-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; vertical-align: middle; }

.kind { font-size: 10px; padding: 2px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.kind.ratable { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.kind.point-in-time { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.kind.milestone { background: rgba(251, 191, 36, .15); color: #fcd34d; }

.cc { width: 100%; height: 160px; margin-top: 12px; }

@media (max-width: 1024px) {
  .row { grid-template-columns: 1fr; }
  .chart { grid-template-columns: repeat(6, 1fr); height: 160px; }
  .col-num { font-size: 9px; }
}
</style>
