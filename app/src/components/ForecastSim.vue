<script setup>
import { ref, computed } from 'vue'
import { saturatingRevenue, project, rebalanceAllocations, optimalAllocation, projectWithUncertainty } from '../logic/forecast.js'

// Each channel: saturating ROAS — diminishing returns model
const channels = ref([
  { id: 'tiktok', name: 'TikTok',  alloc: 32, color: '#fe2c55', k: 4.4, sat: 90 },
  { id: 'meta',   name: 'Meta',    alloc: 28, color: '#1877f2', k: 3.6, sat: 110 },
  { id: 'google', name: 'Google',  alloc: 22, color: '#34a853', k: 2.8, sat: 70 },
  { id: 'youtube',name: 'YouTube', alloc: 12, color: '#ff0000', k: 2.1, sat: 60 },
  { id: 'email',  name: 'Email',   alloc: 6,  color: '#fbbf24', k: 6.2, sat: 14 }
])
const totalBudget = ref(200000)

const allocSum = computed(() => channels.value.reduce((s, c) => s + c.alloc, 0))

function setAlloc(id, val) {
  const next = rebalanceAllocations(channels.value, id, val)
  for (const c of channels.value) c.alloc = next[c.id]
}

const projections = computed(() => {
  const { rows } = project(channels.value, totalBudget.value)
  return channels.value.map((c, i) => ({ ...c, ...rows[i] }))
})

const totalRev = computed(() => project(channels.value, totalBudget.value).totalRevenue)
const totalRoas = computed(() => project(channels.value, totalBudget.value).totalRoas)

// Spec 48 — a point forecast invites overconfidence. Response coefficients
// carry ~20% relative uncertainty; channels are partly correlated (shared
// seasonality/macro), so the portfolio band is narrower than the naive sum.
const CHANNEL_CV = 0.2
const CHANNEL_CORRELATION = 0.3
const level = ref('p80')
const forecast = computed(() => projectWithUncertainty(channels.value, totalBudget.value, {
  cv: CHANNEL_CV, correlation: CHANNEL_CORRELATION, level: level.value
}))
const kFmt = v => '$' + Math.round(v / 1000).toLocaleString() + 'k'

function applyOptimal() {
  const next = optimalAllocation(channels.value, totalBudget.value)
  if (next) for (const c of channels.value) c.alloc = next[c.id]
}

function curvePath(ch, w = 200, h = 60) {
  const maxB = totalBudget.value / 1000
  const maxR = saturatingRevenue(ch, maxB) || 1
  const pts = []
  for (let i = 0; i <= 30; i++) {
    const b = (i / 30) * maxB
    const r = saturatingRevenue(ch, b)
    const x = (b / maxB) * w
    const y = h - (r / maxR) * (h - 4) - 2
    pts.push(`${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
  }
  return pts.join(' ')
}

function dotPos(ch) {
  const budgetK = (totalBudget.value * ch.alloc / 100) / 1000
  const maxB = totalBudget.value / 1000
  const maxR = saturatingRevenue(ch, maxB) || 1
  const x = (budgetK / maxB) * 200
  const y = 60 - (saturatingRevenue(ch, budgetK) / maxR) * 56 - 2
  return { x: x.toFixed(1), y: y.toFixed(1) }
}
</script>

<template>
  <div class="fc">
    <div class="card head">
      <div>
        <div class="kicker">What-if budget simulator</div>
        <h3>Channel allocation · marginal ROAS</h3>
        <p class="meta">Saturating revenue curves. AI water-fills budget until marginal ROAS equalizes across channels.</p>
      </div>
      <div class="kpis">
        <div><div class="kn grad-text">{{ totalRoas.toFixed(2) }}×</div><div class="kl">Total ROAS</div></div>
        <div>
          <div class="kn">{{ kFmt(totalRev) }}</div>
          <div class="kl">Projected revenue</div>
          <div class="band">{{ kFmt(forecast.band.lo) }} – {{ kFmt(forecast.band.hi) }}</div>
        </div>
        <div><div class="kn">${{ (totalBudget / 1000).toLocaleString() }}k</div><div class="kl">Total budget</div></div>
      </div>
    </div>

    <div class="card unc">
      <div class="unc-head">
        <div>
          <div class="kicker">Prediction interval</div>
          <h3>{{ kFmt(forecast.band.lo) }} – {{ kFmt(forecast.band.hi) }}</h3>
          <p class="meta">
            ±{{ (forecast.relativeCv * forecast.band.z * 100).toFixed(1) }}% around
            {{ kFmt(forecast.band.mid) }} · {{ (CHANNEL_CV * 100).toFixed(0) }}% response-curve uncertainty,
            {{ CHANNEL_CORRELATION }} channel correlation. Portfolio CV
            {{ (forecast.relativeCv * 100).toFixed(1) }}% — diversified below the
            {{ (CHANNEL_CV * 100).toFixed(0) }}% per-channel figure.
          </p>
        </div>
        <div class="lvl">
          <button v-for="l in ['p80', 'p90', 'p95']" :key="l" type="button"
            :class="{ on: level === l }" @click="level = l">{{ l.toUpperCase() }}</button>
        </div>
      </div>
      <div class="unc-bar" :title="`${kFmt(forecast.band.lo)} – ${kFmt(forecast.band.hi)}`">
        <div class="unc-range" :style="{
          left: (forecast.band.lo / forecast.band.hi * 100) + '%',
          right: '0%'
        }"></div>
        <div class="unc-mid" :style="{ left: (forecast.band.mid / forecast.band.hi * 100) + '%' }"></div>
      </div>
      <div class="unc-scale">
        <span>{{ kFmt(forecast.band.lo) }}</span>
        <span class="unc-mid-lbl">{{ kFmt(forecast.band.mid) }}</span>
        <span>{{ kFmt(forecast.band.hi) }}</span>
      </div>
    </div>

    <div class="card budget-card">
      <div class="ch-row">
        <h3>Total budget · monthly</h3>
        <button class="btn btn-primary sm" @click="applyOptimal" type="button">↺ Apply AI optimum</button>
      </div>
      <div class="bud-row">
        <input type="range" min="40000" max="500000" step="10000" v-model.number="totalBudget" />
        <span class="bud-num">${{ totalBudget.toLocaleString() }}</span>
      </div>
    </div>

    <div class="card">
      <h3>Per-channel allocation</h3>
      <p class="meta">Move a slider — others rebalance to keep total at 100%.</p>
      <div class="grid">
        <div v-for="p in projections" :key="p.id" class="ch">
          <div class="ch-head">
            <span class="ch-name"><span class="ch-dot" :style="{ background: p.color }"></span>{{ p.name }}</span>
            <span class="ch-alloc">{{ p.alloc }}% · ${{ Math.round(p.budget / 1000) }}k</span>
          </div>
          <input type="range" min="0" max="100" :value="p.alloc" @input="setAlloc(p.id, +$event.target.value)" />
          <div class="ch-curve">
            <svg viewBox="0 0 200 60" preserveAspectRatio="none">
              <path :d="curvePath(p)" fill="none" :stroke="p.color" stroke-width="2" stroke-linecap="round" stroke-opacity=".75" />
              <circle :cx="dotPos(p).x" :cy="dotPos(p).y" r="4" :fill="p.color" stroke="#fff" stroke-width="1.5" />
            </svg>
          </div>
          <div class="ch-foot">
            <div><div class="cn">{{ p.roas.toFixed(2) }}×</div><div class="cl">avg ROAS</div></div>
            <div><div class="cn">{{ p.marginal.toFixed(2) }}×</div><div class="cl">marginal ROAS</div></div>
            <div><div class="cn">${{ Math.round(p.revenue / 1000) }}k</div><div class="cl">revenue</div></div>
          </div>
        </div>
      </div>

      <div class="balance" :class="{ ok: Math.abs(allocSum - 100) < 1 }">
        Allocation sum · {{ allocSum }}% {{ Math.abs(allocSum - 100) < 1 ? '· balanced' : '· rebalancing…' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.fc { display: flex; flex-direction: column; gap: 16px; }
.band { font-size: 11px; color: var(--primary-2); margin-top: 3px; font-variant-numeric: tabular-nums; }
.unc { padding: 16px 18px; }
.unc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.unc-head h3 { margin: 4px 0 6px; font-variant-numeric: tabular-nums; }
.lvl { display: flex; gap: 4px; flex-shrink: 0; }
.lvl button { padding: 5px 11px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text-dim); font-size: 11px; font-weight: 700; cursor: pointer; }
.lvl button.on { border-color: var(--primary); background: rgba(124, 92, 255, .18); color: #fff; }
.lvl button:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.unc-bar { position: relative; height: 12px; border-radius: 999px; background: var(--surface-2); margin-top: 14px; overflow: hidden; }
.unc-range { position: absolute; top: 0; bottom: 0; background: linear-gradient(90deg, rgba(124,92,255,.35), rgba(34,211,238,.45)); }
.unc-mid { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--text); }
.unc-scale { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-dim); margin-top: 6px; font-variant-numeric: tabular-nums; }
.unc-mid-lbl { color: var(--text); font-weight: 700; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.kpis { display: flex; gap: 20px; }
.kn { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.kl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.budget-card { padding: 18px 20px; }
.ch-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.btn.sm { padding: 6px 12px; font-size: 12px; }
.bud-row { display: flex; align-items: center; gap: 14px; }
.bud-row input[type="range"] { flex: 1; accent-color: var(--primary); }
.bud-num { font-weight: 800; font-variant-numeric: tabular-nums; font-size: 17px; min-width: 120px; text-align: right; }

.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-top: 12px; }
.ch { padding: 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.ch-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ch-name { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13px; }
.ch-dot { width: 10px; height: 10px; border-radius: 50%; }
.ch-alloc { font-weight: 700; font-variant-numeric: tabular-nums; font-size: 13px; }
.ch input[type="range"] { width: 100%; accent-color: var(--primary); margin-bottom: 8px; }
.ch-curve svg { width: 100%; height: 60px; background: var(--bg-2); border-radius: 8px; padding: 4px; box-sizing: content-box; }
.ch-foot { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border); }
.cn { font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; }
.cl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; margin-top: 2px; }

.balance { margin-top: 14px; padding: 8px 12px; border-radius: 8px; background: var(--surface-2); color: var(--text-dim); font-size: 12px; text-align: right; }
.balance.ok { color: var(--success); }

@media (max-width: 1024px) { .grid { grid-template-columns: 1fr; } }
</style>
