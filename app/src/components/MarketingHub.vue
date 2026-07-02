<script setup>
import { ref, computed } from 'vue'

const range = ref('7d')
const ranges = [{ v: '24h', l: '24h' }, { v: '7d', l: '7d' }, { v: '30d', l: '30d' }, { v: '90d', l: '90d' }]

const kpis = computed(() => {
  const mult = { '24h': 0.14, '7d': 1, '30d': 4.2, '90d': 12.6 }[range.value]
  return [
    { k: 'Spend', v: `$${Math.round(48230 * mult).toLocaleString()}`, d: '+12.4%', up: true,  spark: '12,18,16,22,24,30,28' },
    { k: 'ROAS', v: `${(3.4 + (range.value === '24h' ? -0.2 : 0)).toFixed(1)}×`, d: '+0.4×',  up: true,  spark: '8,12,14,12,16,18,22' },
    { k: 'CTR',  v: `${(2.8).toFixed(2)}%`,  d: '+0.6pt', up: true,  spark: '6,10,12,14,12,18,22' },
    { k: 'CVR',  v: `${(3.1).toFixed(2)}%`,  d: '−0.2pt', up: false, spark: '14,16,18,12,14,10,12' },
    { k: 'Purchases', v: Math.round(2840 * mult).toLocaleString(), d: '+18.7%', up: true,  spark: '10,12,14,16,20,22,26' },
    { k: 'CPA',  v: `$${Math.round(17 - mult / 2)}`, d: '−$3', up: true,  spark: '24,22,18,16,14,12,10' }
  ]
})

const channels = [
  { name: 'Meta',         spend: 18200, roas: 3.8, color: '#1877F2' },
  { name: 'TikTok',       spend: 14600, roas: 4.2, color: '#FE2C55' },
  { name: 'Google',       spend: 9800,  roas: 2.6, color: '#34A853' },
  { name: 'YouTube',      spend: 5630,  roas: 2.1, color: '#FF0000' }
]
const totalSpend = computed(() => channels.reduce((s, c) => s + c.spend, 0))

const spend7 = [12000, 14200, 9800, 16400, 15200, 18800, 22600]

const funnel = [
  { stage: 'Impressions',   val: 1840000, color: 'linear-gradient(90deg,#7c5cff,#22d3ee)' },
  { stage: 'Clicks',        val:  51520,  color: 'linear-gradient(90deg,#22d3ee,#34d399)' },
  { stage: 'Add to cart',   val:   7864,  color: 'linear-gradient(90deg,#34d399,#fbbf24)' },
  { stage: 'Purchase',      val:   1597,  color: 'linear-gradient(90deg,#fbbf24,#ff7ad9)' }
]

const creatives = [
  { name: 'Lumi · Before/After v3',  status: 'winning', ctr: 5.2, roas: 4.8, market: 'JP / KR', c1: '#7c5cff', c2: '#22d3ee' },
  { name: 'Sneaker · Style Swap',    status: 'winning', ctr: 4.8, roas: 3.6, market: 'US',      c1: '#ff7ad9', c2: '#7c5cff' },
  { name: 'SaaS · 12s Demo',         status: 'testing', ctr: 2.6, roas: 2.4, market: 'US / EU', c1: '#22d3ee', c2: '#34d399' },
  { name: 'Food · Recipe Bumper',    status: 'testing', ctr: 3.8, roas: 1.9, market: 'SEA',     c1: '#fbbf24', c2: '#ff7ad9' },
  { name: 'Gadget · ASMR Unboxing',  status: 'paused',  ctr: 1.8, roas: 0.9, market: 'JP',      c1: '#60a5fa', c2: '#7c5cff' },
  { name: 'Apparel · Lookbook',      status: 'winning', ctr: 4.2, roas: 3.2, market: 'EU',      c1: '#34d399', c2: '#22d3ee' }
]

const insights = [
  { tag: 'Opportunity', text: 'TikTok creative #LumiV3 outperforms baseline by 38% — recommend +20% budget shift.' },
  { tag: 'Risk',        text: 'YouTube CPA up 24% over last 3 days. Pause underperforming variants in BR.' },
  { tag: 'Localize',    text: 'JP audience responds to UGC hooks 2.1× vs. studio shots. Generate 4 UGC variants.' }
]

function sparkPath(csv, w = 80, h = 24) {
  const arr = csv.split(',').map(Number)
  const max = Math.max(...arr), min = Math.min(...arr)
  const dx = w / (arr.length - 1)
  return arr.map((v, i) => {
    const x = i * dx
    const y = h - ((v - min) / (max - min || 1)) * (h - 4) - 2
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

function barH(v) {
  const max = Math.max(...spend7)
  return Math.max(6, (v / max) * 100)
}
</script>

<template>
  <div class="hub">
    <div class="bar-row">
      <div>
        <h3>Performance · last {{ range }}</h3>
        <p class="meta">Across 4 channels, 8 markets, 42 active campaigns</p>
      </div>
      <div class="range">
        <button v-for="r in ranges" :key="r.v" :class="{ on: range === r.v }" @click="range = r.v" type="button">{{ r.l }}</button>
      </div>
    </div>

    <div class="kpi-grid">
      <div v-for="k in kpis" :key="k.k" class="card kpi">
        <div class="kk">{{ k.k }}</div>
        <div class="kv">{{ k.v }}</div>
        <div class="krow">
          <span class="kd" :class="k.up ? 'up' : 'down'">{{ k.up ? '▲' : '▼' }} {{ k.d }}</span>
          <svg viewBox="0 0 80 24" class="spark" preserveAspectRatio="none">
            <path :d="sparkPath(k.spark)" fill="none" :stroke="k.up ? 'var(--success)' : 'var(--danger)'" stroke-width="2" stroke-linecap="round" />
          </svg>
        </div>
      </div>
    </div>

    <div class="row2">
      <div class="card">
        <h3>Spend · 7 days</h3>
        <div class="chart">
          <div v-for="(v, i) in spend7" :key="i" class="bar-col">
            <div class="bar-fill" :style="{ height: barH(v) + '%' }"></div>
            <div class="bar-lbl">${{ Math.round(v / 1000) }}k</div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Channel mix</h3>
        <div class="channels">
          <div v-for="c in channels" :key="c.name" class="ch">
            <div class="ch-row">
              <span class="ch-name"><span class="ch-dot" :style="{ background: c.color }"></span>{{ c.name }}</span>
              <span class="ch-vals">${{ (c.spend / 1000).toFixed(1) }}k · {{ c.roas.toFixed(1) }}×</span>
            </div>
            <div class="ch-track"><div class="ch-fill" :style="{ width: (c.spend / totalSpend * 100) + '%', background: c.color }"></div></div>
          </div>
        </div>
      </div>
    </div>

    <div class="row2">
      <div class="card">
        <h3>Conversion funnel</h3>
        <div class="funnel">
          <div v-for="(s, i) in funnel" :key="s.stage" class="fr">
            <div class="fr-meta">
              <span>{{ s.stage }}</span>
              <span>{{ s.val.toLocaleString() }}</span>
            </div>
            <div class="fr-bar" :style="{ width: ((s.val / funnel[0].val) * 100) + '%', background: s.color }"></div>
            <div class="fr-rate" v-if="i > 0">{{ ((s.val / funnel[i-1].val) * 100).toFixed(1) }}% step rate</div>
          </div>
        </div>
      </div>

      <div class="card insights">
        <h3>AI insights</h3>
        <div v-for="(it, i) in insights" :key="i" class="ins" :class="it.tag.toLowerCase()">
          <div class="ins-tag">{{ it.tag }}</div>
          <div class="ins-text">{{ it.text }}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="lib-head">
        <h3>Creative library</h3>
        <div class="lib-actions">
          <button class="btn btn-ghost sm" type="button">Filter</button>
          <button class="btn btn-primary sm" type="button">+ New variant</button>
        </div>
      </div>
      <div class="lib">
        <div v-for="cr in creatives" :key="cr.name" class="tile">
          <div class="thumb" :style="{ background: `linear-gradient(135deg, ${cr.c1}, ${cr.c2})` }">
            <span class="status" :class="cr.status">{{ cr.status }}</span>
          </div>
          <div class="tile-body">
            <div class="tn">{{ cr.name }}</div>
            <div class="tm">{{ cr.market }}</div>
            <div class="tk"><span>CTR <strong>{{ cr.ctr }}%</strong></span><span>ROAS <strong>{{ cr.roas }}×</strong></span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hub { display: flex; flex-direction: column; gap: 20px; }
.bar-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.meta { color: var(--text-dim); margin: 4px 0 0; }
.range { display: inline-flex; padding: 4px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; }
.range button { padding: 6px 14px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 13px; font-weight: 600; }
.range button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.kpi-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
.kpi { padding: 18px; }
.kk { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.kv { font-size: 24px; font-weight: 800; margin: 6px 0 8px; font-variant-numeric: tabular-nums; }
.krow { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.kd { font-size: 11px; }
.kd.up { color: var(--success); }
.kd.down { color: var(--danger); }
.spark { width: 60px; height: 22px; }

.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }

.chart { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; height: 180px; align-items: end; margin-top: 16px; }
.bar-col { display: flex; flex-direction: column; align-items: center; gap: 8px; height: 100%; }
.bar-fill { width: 100%; background: linear-gradient(180deg, var(--primary), var(--primary-2)); border-radius: 6px 6px 0 0; transition: height .3s ease; min-height: 6px; }
.bar-col { justify-content: flex-end; }
.bar-lbl { font-size: 11px; color: var(--text-dim); }

.channels { display: flex; flex-direction: column; gap: 14px; margin-top: 16px; }
.ch-row { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px; }
.ch-name { display: inline-flex; align-items: center; gap: 8px; }
.ch-dot { width: 10px; height: 10px; border-radius: 3px; }
.ch-vals { color: var(--text-dim); font-variant-numeric: tabular-nums; }
.ch-track { height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.ch-fill { height: 100%; border-radius: 999px; }

.funnel { display: flex; flex-direction: column; gap: 14px; margin-top: 16px; }
.fr-meta { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
.fr-bar { height: 14px; border-radius: 6px; min-width: 12%; }
.fr-rate { font-size: 11px; color: var(--text-dim); margin-top: 4px; }

.insights { display: flex; flex-direction: column; gap: 12px; }
.ins { padding: 12px 14px; border-radius: 10px; background: var(--surface); border-left: 3px solid var(--primary); }
.ins.opportunity { border-color: var(--success); }
.ins.risk { border-color: var(--danger); }
.ins.localize { border-color: var(--primary-2); }
.ins-tag { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 4px; }
.ins-text { font-size: 13px; }

.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.lib-actions { display: flex; gap: 8px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }
.lib { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.tile { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--surface); }
.thumb { aspect-ratio: 16 / 9; position: relative; display: flex; align-items: flex-start; justify-content: flex-end; padding: 10px; }
.status { font-size: 10px; padding: 4px 8px; border-radius: 999px; background: rgba(0,0,0,.5); color: #fff; text-transform: uppercase; letter-spacing: .08em; border: 1px solid rgba(255,255,255,.15); }
.status.winning { background: rgba(52, 211, 153, .25); color: #6ee7b7; border-color: rgba(52, 211, 153, .4); }
.status.testing { background: rgba(251, 191, 36, .25); color: #fcd34d; border-color: rgba(251, 191, 36, .4); }
.status.paused { background: rgba(255,255,255,.1); color: #d1d5db; }
.tile-body { padding: 12px 14px; }
.tn { font-weight: 600; font-size: 14px; }
.tm { color: var(--text-dim); font-size: 12px; margin: 2px 0 8px; }
.tk { display: flex; gap: 14px; font-size: 12px; color: var(--text-dim); }
.tk strong { color: var(--text); font-variant-numeric: tabular-nums; }

@media (max-width: 1100px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 900px) {
  .row2 { grid-template-columns: 1fr; }
  .lib { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 540px) {
  .kpi-grid { grid-template-columns: 1fr 1fr; }
  .lib { grid-template-columns: 1fr; }
}
</style>
