<script setup>
import { ref, computed } from 'vue'
import { attribute, attributionRows } from '../logic/attribution.js'

const model = ref('shapley')
const models = [
  { v: 'last',     label: 'Last-touch',    note: 'All credit to the final touchpoint before conversion.' },
  { v: 'first',    label: 'First-touch',   note: 'All credit to the discovery touchpoint.' },
  { v: 'linear',   label: 'Linear',        note: 'Equal credit across all touches.' },
  { v: 'decay',    label: 'Time-decay',    note: 'Half-life of 7 days; recent touches weigh more.' },
  { v: 'position', label: 'Position-based',note: '40% first, 40% last, 20% split across middle.' },
  { v: 'shapley',  label: 'Shapley',       note: 'Game-theoretic credit across all touchpoint coalitions.' }
]

// Spec 46 — aggregated conversion paths (path rollup). Every number on this
// screen is COMPUTED from these journeys; nothing is a hardcoded split.
const DAY = 86400000
const CONVERTED_AT = 100 * DAY
const PATHS = [
  { count: 607, steps: [['TikTok', 21], ['Meta · Reel', 9], ['Direct', 0]] },
  { count: 351, steps: [['Google · YouTube', 17], ['Email · Lifecycle', 5], ['Direct', 0]] },
  { count: 272, steps: [['TikTok', 28], ['Google · YouTube', 14], ['Email · Lifecycle', 4], ['Direct', 0]] },
  { count: 158, steps: [['Meta · Search', 11], ['Meta · Reel', 0]] },
  { count:  96, steps: [['TikTok', 6], ['Meta · Search', 0]] },
  { count:  63, steps: [['Email · Lifecycle', 0]] },
  { count:  50, steps: [['Meta · Search', 19], ['Meta · Reel', 8], ['Email · Lifecycle', 0]] }
]

const journeys = PATHS.map(p => ({
  count: p.count,
  convertedAt: CONVERTED_AT,
  touches: p.steps.map(([channel, daysBefore]) => ({ channel, at: CONVERTED_AT - daysBefore * DAY }))
}))

const conversions = journeys.reduce((s, j) => s + j.count, 0)
const revenue = 247800

const rows = computed(() => attributionRows(journeys, model.value, { halfLifeDays: 7 }))
const cumulative = computed(() => {
  let acc = 0
  return rows.value.map(r => { acc += r.pct; return acc })
})

// Over/under-credit versus a naive last-touch view — the point of the panel.
const lastTouch = computed(() => attribute(journeys, 'last'))
const deltas = computed(() => rows.value.map(r => ({
  channel: r.channel,
  pct: r.pct,
  delta: r.pct - (lastTouch.value[r.channel] ?? 0) * 100
})))

const topPaths = computed(() =>
  [...PATHS].sort((a, b) => b.count - a.count).slice(0, 3).map(p => ({
    count: p.count,
    share: (p.count / conversions) * 100,
    steps: p.steps.map(([channel]) => channel)
  }))
)
</script>

<template>
  <div class="attr">
    <div class="card head">
      <div>
        <div class="kicker">Multi-touch attribution</div>
        <h3>Conversion credit by channel</h3>
        <p class="meta">Last 30 days · {{ conversions.toLocaleString() }} conversions · ${{ revenue.toLocaleString() }} revenue</p>
      </div>
      <div class="model-pick">
        <button v-for="m in models" :key="m.v" :class="{ on: model === m.v }" @click="model = m.v" type="button">{{ m.label }}</button>
      </div>
    </div>

    <div class="card chart">
      <div class="hh">
        <h3>{{ models.find(m => m.v === model).label }}</h3>
        <span class="meta">{{ models.find(m => m.v === model).note }}</span>
      </div>
      <div class="bars">
        <div v-for="(r, i) in rows" :key="r.channel" class="brow">
          <span class="bch">{{ r.channel }}</span>
          <div class="bw">
            <div class="bf" :style="{ width: Math.max(2, r.pct * 3) + '%' }">
              <span class="bv">{{ r.pct.toFixed(1) }}%</span>
            </div>
            <span class="bcum">cum {{ cumulative[i].toFixed(1) }}%</span>
          </div>
          <span class="brev">${{ Math.round(revenue * r.credit).toLocaleString() }}</span>
        </div>
      </div>
      <div class="legend">
        <span v-if="rows.length"><span class="dot top"></span>Top channel · {{ rows[0].channel }} ({{ rows[0].pct.toFixed(1) }}%)</span>
        <span>Total · {{ rows.reduce((s, r) => s + r.pct, 0).toFixed(0) }}%</span>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>Customer journey · top 3 paths</h3>
        <div class="paths">
          <div v-for="(p, pi) in topPaths" :key="pi" class="path">
            <div class="p-meta">
              <span class="p-share">{{ p.share.toFixed(0) }}%</span>
              <span class="p-count">{{ p.count }} conv</span>
            </div>
            <div class="p-flow">
              <template v-for="(s, si) in p.steps" :key="si">
                <span class="step">{{ s }}</span>
                <span v-if="si < p.steps.length - 1" class="arr">→</span>
              </template>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Delta vs last-touch</h3>
        <p class="meta">How much each channel is over/under-credited if you only look at last-touch.</p>
        <div class="delta">
          <div v-for="d in deltas" :key="d.channel" class="dr">
            <span class="d-ch">{{ d.channel }}</span>
            <div class="d-bar">
              <div class="d-mid"></div>
              <div class="d-fill"
                :class="d.delta >= 0 ? 'pos' : 'neg'"
                :style="{
                  width: Math.min(50, Math.abs(d.delta) * 1.2) + '%',
                  marginLeft: d.delta >= 0 ? '50%' : `calc(50% - ${Math.min(50, Math.abs(d.delta) * 1.2)}%)`
                }">
              </div>
            </div>
            <span class="d-num" :class="d.delta >= 0 ? 'pos' : 'neg'">{{ d.delta >= 0 ? '+' : '' }}{{ d.delta.toFixed(1) }}pt</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.attr { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.model-pick { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; flex-wrap: wrap; max-width: 100%; }
.model-pick button { padding: 5px 10px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 11px; font-weight: 600; }
.model-pick button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.chart { padding: 20px; }
.hh { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; gap: 16px; flex-wrap: wrap; }
.hh .meta { margin: 0; max-width: 60%; text-align: right; }
.bars { display: flex; flex-direction: column; gap: 8px; }
.brow { display: grid; grid-template-columns: 140px 1fr 100px; gap: 12px; align-items: center; }
.bch { font-size: 13px; color: var(--text); }
.bw { display: flex; align-items: center; gap: 10px; }
.bf { height: 28px; background: linear-gradient(90deg, var(--primary), var(--primary-2)); border-radius: 6px; display: flex; align-items: center; padding-left: 10px; min-width: 30px; transition: width .3s; }
.bv { color: #fff; font-weight: 700; font-size: 12px; font-variant-numeric: tabular-nums; }
.bcum { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.brev { text-align: right; font-variant-numeric: tabular-nums; font-size: 13px; font-weight: 600; }

.legend { display: flex; gap: 24px; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-dim); flex-wrap: wrap; }
.legend .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.legend .dot.top { background: var(--success); }

.row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.paths { display: flex; flex-direction: column; gap: 14px; margin-top: 12px; }
.path { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.p-meta { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
.p-share { font-size: 14px; font-weight: 800; color: var(--primary-2); }
.p-count { font-size: 11px; color: var(--text-dim); }
.p-flow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.step { padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; }
.step.tt { background: rgba(254, 44, 85, .15); color: #fda4af; }
.step.meta { background: rgba(24, 119, 242, .15); color: #93c5fd; }
.step.google { background: rgba(52, 168, 83, .15); color: #6ee7b7; }
.step.email { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.step.direct { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.arr { color: var(--text-dim); }

.delta { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
.dr { display: grid; grid-template-columns: 120px 1fr 60px; gap: 12px; align-items: center; font-size: 13px; }
.d-ch { color: var(--text); }
.d-bar { position: relative; height: 16px; background: var(--surface-2); border-radius: 4px; overflow: hidden; }
.d-mid { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--border); }
.d-fill { height: 100%; }
.d-fill.pos { background: linear-gradient(90deg, var(--primary-2), var(--success)); }
.d-fill.neg { background: linear-gradient(90deg, var(--danger), #fcd34d); }
.d-num { text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; font-size: 12px; }
.d-num.pos { color: var(--success); }
.d-num.neg { color: var(--danger); }

@media (max-width: 900px) {
  .row { grid-template-columns: 1fr; }
  .brow { grid-template-columns: 100px 1fr 80px; }
}
</style>
