<script setup>
import { ref, computed } from 'vue'

const cohorts = ref([
  { week: 'W42', size: 8420, market: 'US' },
  { week: 'W43', size: 9120, market: 'US' },
  { week: 'W44', size: 12480, market: 'JP' },
  { week: 'W45', size: 14210, market: 'JP' },
  { week: 'W46', size: 11680, market: 'KR' },
  { week: 'W47', size: 13420, market: 'BR' },
  { week: 'W48', size: 16240, market: 'BR' },
  { week: 'W49', size: 18420, market: 'SEA' }
])

// Synthetic retention curves: starts ~100%, decays with cohort-dependent rate
function retentionRow(i, size) {
  const baseDecay = 0.78 + ((i % 4) * 0.03)
  const stickiness = 0.32 + ((i % 3) * 0.02)
  const row = []
  for (let w = 0; w < 8; w++) {
    if (w === 0) row.push(100)
    else {
      const decay = stickiness + (1 - stickiness) * Math.pow(baseDecay, w)
      row.push(Math.round(decay * 100))
    }
  }
  return row
}

const matrix = computed(() => cohorts.value.map((c, i) => retentionRow(i, c.size)))

function cellColor(v) {
  if (v >= 80) return 'p-90'
  if (v >= 60) return 'p-70'
  if (v >= 45) return 'p-55'
  if (v >= 30) return 'p-40'
  return 'p-25'
}

const overlay = ref([0, 2, 7])
function toggleOverlay(i) {
  const idx = overlay.value.indexOf(i)
  if (idx >= 0) overlay.value.splice(idx, 1)
  else if (overlay.value.length < 4) overlay.value.push(i)
}

const colors = ['#7c5cff', '#22d3ee', '#ff7ad9', '#34d399']
function curvePath(row, w = 320, h = 120) {
  const dx = w / (row.length - 1)
  return row.map((v, i) => {
    const x = i * dx
    const y = h - ((v - 20) / 80) * (h - 8) - 4
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

const summary = computed(() => {
  const w1 = matrix.value.map(r => r[1]); const avgW1 = Math.round(w1.reduce((a,b) => a+b, 0) / w1.length)
  const w4 = matrix.value.map(r => r[4]); const avgW4 = Math.round(w4.reduce((a,b) => a+b, 0) / w4.length)
  const w7 = matrix.value.map(r => r[7]); const avgW7 = Math.round(w7.reduce((a,b) => a+b, 0) / w7.length)
  return { w1: avgW1, w4: avgW4, w7: avgW7 }
})
</script>

<template>
  <div class="ret">
    <div class="card head">
      <div>
        <div class="kicker">Cohort retention</div>
        <h3>Weekly retention by acquisition cohort</h3>
        <p class="meta">{{ cohorts.length }} cohorts · weeks since acquisition</p>
      </div>
      <div class="kpis">
        <div><div class="kn grad-text">{{ summary.w1 }}%</div><div class="kl">avg W1</div></div>
        <div><div class="kn">{{ summary.w4 }}%</div><div class="kl">avg W4</div></div>
        <div><div class="kn">{{ summary.w7 }}%</div><div class="kl">avg W7</div></div>
      </div>
    </div>

    <div class="card">
      <h3>Heatmap</h3>
      <p class="meta">Click any cohort row to overlay its retention curve below.</p>
      <div class="heatmap">
        <div class="hm-head">
          <span class="hm-corner"></span>
          <span v-for="w in 8" :key="w" class="hm-h">W+{{ w - 1 }}</span>
        </div>
        <div v-for="(row, ri) in matrix" :key="ri" class="hm-row" :class="{ on: overlay.includes(ri) }" @click="toggleOverlay(ri)">
          <div class="hm-lbl">
            <div class="hm-w">{{ cohorts[ri].week }}</div>
            <div class="hm-m">{{ cohorts[ri].market }} · {{ (cohorts[ri].size / 1000).toFixed(1) }}k</div>
          </div>
          <div v-for="(v, ci) in row" :key="ci" class="hm-cell" :class="cellColor(v)">{{ v }}</div>
        </div>
      </div>
    </div>

    <div class="card curves">
      <div class="ch-row">
        <h3>Retention curves</h3>
        <span class="meta">{{ overlay.length }} cohort{{ overlay.length === 1 ? '' : 's' }} overlaid</span>
      </div>
      <svg viewBox="0 0 380 140" class="cc" preserveAspectRatio="none">
        <g stroke="var(--border)" stroke-dasharray="3 3" stroke-width="1">
          <line x1="40" y1="20" x2="380" y2="20" />
          <line x1="40" y1="60" x2="380" y2="60" />
          <line x1="40" y1="100" x2="380" y2="100" />
        </g>
        <g fill="var(--text-dim)" font-size="9">
          <text x="36" y="22" text-anchor="end">100%</text>
          <text x="36" y="62" text-anchor="end">60%</text>
          <text x="36" y="102" text-anchor="end">20%</text>
        </g>
        <g v-for="(ri, idx) in overlay" :key="ri" :transform="`translate(40, 0)`">
          <path :d="curvePath(matrix[ri], 320, 120)" fill="none" :stroke="colors[idx]" stroke-width="2.5" stroke-linecap="round" />
          <g v-for="(v, wi) in matrix[ri]" :key="wi">
            <circle :cx="(wi / 7) * 320" :cy="120 - ((v - 20) / 80) * 112 - 4" r="3" :fill="colors[idx]" />
          </g>
        </g>
      </svg>
      <div class="ov-legend">
        <span v-for="(ri, idx) in overlay" :key="ri" class="ov-it">
          <span class="ov-dot" :style="{ background: colors[idx] }"></span>
          {{ cohorts[ri].week }} · {{ cohorts[ri].market }}
        </span>
        <span v-if="!overlay.length" class="dimc-i">Click a row above to plot a curve.</span>
      </div>

      <div class="leg">
        <span><span class="cell p-90 inline"></span>≥80%</span>
        <span><span class="cell p-70 inline"></span>60–79%</span>
        <span><span class="cell p-55 inline"></span>45–59%</span>
        <span><span class="cell p-40 inline"></span>30–44%</span>
        <span><span class="cell p-25 inline"></span>&lt;30%</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ret { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.kpis { display: flex; gap: 20px; }
.kn { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.kl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.heatmap { display: flex; flex-direction: column; gap: 4px; margin-top: 14px; overflow-x: auto; }
.hm-head { display: grid; grid-template-columns: 110px repeat(8, 1fr); gap: 4px; }
.hm-corner { background: transparent; }
.hm-h { padding: 6px 0; text-align: center; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; font-weight: 700; }
.hm-row { display: grid; grid-template-columns: 110px repeat(8, 1fr); gap: 4px; cursor: pointer; border-radius: 6px; padding: 2px; transition: background .15s; }
.hm-row:hover { background: rgba(124, 92, 255, .06); }
.hm-row.on { background: rgba(124, 92, 255, .12); outline: 1px solid rgba(124, 92, 255, .35); }
.hm-lbl { display: flex; flex-direction: column; justify-content: center; padding: 0 8px; }
.hm-w { font-weight: 700; font-size: 13px; }
.hm-m { font-size: 11px; color: var(--text-dim); }
.hm-cell, .cell { display: grid; place-items: center; aspect-ratio: 1; border-radius: 4px; font-size: 12px; font-variant-numeric: tabular-nums; color: #fff; font-weight: 600; min-height: 34px; }
.cell.inline { display: inline-block; width: 14px; height: 14px; min-height: 0; vertical-align: middle; margin-right: 6px; }
.p-90 { background: #2563eb; }
.p-70 { background: #4f46e5; }
.p-55 { background: #7c5cff; }
.p-40 { background: #a78bfa; color: #1a1a2e; }
.p-25 { background: #c4b5fd; color: #1a1a2e; }

.curves { padding: 20px; }
.ch-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
.cc { width: 100%; height: 180px; margin-bottom: 12px; }
.ov-legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; margin-bottom: 16px; }
.ov-it { display: inline-flex; align-items: center; }
.ov-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.dimc-i { color: var(--text-dim); font-style: italic; }
.leg { display: flex; gap: 14px; flex-wrap: wrap; padding-top: 12px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-dim); }

@media (max-width: 720px) {
  .heatmap { min-width: 600px; }
  .kpis { gap: 12px; }
}
</style>
