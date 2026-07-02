<script setup>
import { ref, computed } from 'vue'

const model = ref('shapley')
const models = [
  { v: 'last',     label: 'Last-touch',    note: 'All credit to the final touchpoint before conversion.' },
  { v: 'first',    label: 'First-touch',   note: 'All credit to the discovery touchpoint.' },
  { v: 'linear',   label: 'Linear',        note: 'Equal credit across all touches.' },
  { v: 'decay',    label: 'Time-decay',    note: 'Half-life of 7 days; recent touches weigh more.' },
  { v: 'position', label: 'Position-based',note: '40% first, 40% last, 20% split across middle.' },
  { v: 'shapley',  label: 'Shapley',       note: 'Game-theoretic credit across all touchpoint coalitions.' },
  { v: 'datadriven', label: 'Data-driven', note: 'Learned credit via counterfactual lift modeling.' }
]

const channels = ['TikTok', 'Meta · Search', 'Meta · Reel', 'Google · YouTube', 'Email · Lifecycle', 'Direct']

const splits = {
  last:        [12, 18, 22, 14, 24, 10],
  first:       [38, 16, 12, 18, 6,  10],
  linear:      [22, 17, 16, 18, 14, 13],
  decay:       [14, 18, 22, 16, 22, 8],
  position:    [28, 14, 14, 16, 18, 10],
  shapley:     [26, 19, 17, 15, 16, 7],
  datadriven:  [30, 21, 14, 14, 17, 4]
}

const credit = computed(() => splits[model.value])
const cumulative = computed(() => {
  let acc = 0
  return credit.value.map(v => { acc += v; return acc })
})

const conversions = 1597
const revenue = 247800

function bar(v) { return Math.max(8, v * 4) }
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
        <div v-for="(c, i) in channels" :key="c" class="brow">
          <span class="bch">{{ c }}</span>
          <div class="bw">
            <div class="bf" :style="{ width: (credit[i] * 3) + '%' }">
              <span class="bv">{{ credit[i] }}%</span>
            </div>
            <span class="bcum">cum {{ cumulative[i] }}%</span>
          </div>
          <span class="brev">${{ Math.round(revenue * credit[i] / 100).toLocaleString() }}</span>
        </div>
      </div>
      <div class="legend">
        <span><span class="dot top"></span>Top channel · {{ channels[credit.indexOf(Math.max(...credit))] }} ({{ Math.max(...credit) }}%)</span>
        <span>Total · {{ credit.reduce((s, v) => s + v, 0) }}%</span>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>Customer journey · top 3 paths</h3>
        <div class="paths">
          <div class="path">
            <div class="p-meta"><span class="p-share">38%</span><span class="p-count">607 conv</span></div>
            <div class="p-flow">
              <span class="step tt">TikTok</span><span class="arr">→</span>
              <span class="step meta">Meta · Reel</span><span class="arr">→</span>
              <span class="step direct">Direct</span>
            </div>
          </div>
          <div class="path">
            <div class="p-meta"><span class="p-share">22%</span><span class="p-count">351 conv</span></div>
            <div class="p-flow">
              <span class="step google">Google</span><span class="arr">→</span>
              <span class="step email">Email</span><span class="arr">→</span>
              <span class="step direct">Direct</span>
            </div>
          </div>
          <div class="path">
            <div class="p-meta"><span class="p-share">17%</span><span class="p-count">272 conv</span></div>
            <div class="p-flow">
              <span class="step tt">TikTok</span><span class="arr">→</span>
              <span class="step google">Google · YT</span><span class="arr">→</span>
              <span class="step email">Email</span><span class="arr">→</span>
              <span class="step direct">Direct</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Delta vs last-touch</h3>
        <p class="meta">How much each channel is over/under-credited if you only look at last-touch.</p>
        <div class="delta">
          <div v-for="(c, i) in channels" :key="c" class="dr">
            <span class="d-ch">{{ c }}</span>
            <div class="d-bar">
              <div class="d-mid"></div>
              <div class="d-fill"
                :class="credit[i] >= splits.last[i] ? 'pos' : 'neg'"
                :style="{
                  width: Math.abs(credit[i] - splits.last[i]) * 4 + '%',
                  marginLeft: credit[i] >= splits.last[i] ? '50%' : `calc(50% - ${Math.abs(credit[i] - splits.last[i]) * 4}%)`
                }">
              </div>
            </div>
            <span class="d-num" :class="credit[i] >= splits.last[i] ? 'pos' : 'neg'">{{ credit[i] >= splits.last[i] ? '+' : '' }}{{ credit[i] - splits.last[i] }}pt</span>
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
