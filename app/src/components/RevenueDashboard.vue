<script setup>
import { computed } from 'vue'

const mrr = 384000
const arr = mrr * 12
const lastMrr = 360000
const mom = ((mrr - lastMrr) / lastMrr) * 100

const waterfall = [
  { k: 'Starting MRR', value: lastMrr, kind: 'start' },
  { k: '+ New',          value: 24000, kind: 'pos' },
  { k: '+ Expansion',    value: 18000, kind: 'pos' },
  { k: '+ Reactivation', value: 4200,  kind: 'pos' },
  { k: '− Contraction',  value: 14400, kind: 'neg' },
  { k: '− Churn',        value: 7800,  kind: 'neg' },
  { k: 'Ending MRR',     value: mrr,   kind: 'end' }
]

const plans = [
  { name: 'Enterprise', accts: 24, mrr: 246000, color: '#7c5cff' },
  { name: 'Scale',      accts: 18, mrr: 84600,  color: '#22d3ee' },
  { name: 'Growth',     accts: 62, mrr: 49600,  color: '#34d399' },
  { name: 'Starter',    accts: 184, mrr: 3800,   color: '#fcd34d' }
]

const cohorts = [
  { quarter: 'Q1 FY26', size: 28, retained: 25, expansion: 132 },
  { quarter: 'Q4 FY25', size: 42, retained: 36, expansion: 124 },
  { quarter: 'Q3 FY25', size: 58, retained: 46, expansion: 118 },
  { quarter: 'Q2 FY25', size: 64, retained: 48, expansion: 110 }
]

const nrr = 116
const grr = 92
const totalMrr = plans.reduce((s, p) => s + p.mrr, 0)

// Compute cumulative for waterfall positioning
const waterfallPos = computed(() => {
  const max = lastMrr + 50000
  let running = 0
  return waterfall.map((w, i) => {
    if (w.kind === 'start') {
      const r = { ...w, bottom: 0, height: (w.value / max) * 100, label: `$${(w.value / 1000).toFixed(0)}k` }
      running = w.value
      return r
    }
    if (w.kind === 'end') {
      return { ...w, bottom: 0, height: (w.value / max) * 100, label: `$${(w.value / 1000).toFixed(0)}k` }
    }
    if (w.kind === 'pos') {
      const r = { ...w, bottom: (running / max) * 100, height: (w.value / max) * 100, label: `+$${(w.value / 1000).toFixed(1)}k` }
      running += w.value
      return r
    }
    // neg
    running -= w.value
    return { ...w, bottom: (running / max) * 100, height: (w.value / max) * 100, label: `−$${(w.value / 1000).toFixed(1)}k` }
  })
})
</script>

<template>
  <div class="rd">
    <div class="card head">
      <div>
        <div class="kicker">SaaS revenue · period close · Nov 30</div>
        <h3>Subscription revenue health</h3>
        <p class="meta">Real-time MRR ledger, materialized from Stripe + Recurly + invoiced legacy contracts.</p>
      </div>
    </div>

    <div class="kpi-row">
      <div class="card kpi">
        <div class="kk">MRR</div>
        <div class="kv grad-text">${{ Math.round(mrr / 1000).toLocaleString() }}k</div>
        <div class="kd up">▲ +{{ mom.toFixed(1) }}% MoM</div>
      </div>
      <div class="card kpi">
        <div class="kk">ARR</div>
        <div class="kv">${{ (arr / 1e6).toFixed(2) }}M</div>
        <div class="kd dimc">12 × MRR</div>
      </div>
      <div class="card kpi">
        <div class="kk">NRR · 12mo</div>
        <div class="kv" :class="nrr >= 110 ? 'up' : ''">{{ nrr }}%</div>
        <div class="kd up">expansion > churn</div>
      </div>
      <div class="card kpi">
        <div class="kk">GRR · 12mo</div>
        <div class="kv">{{ grr }}%</div>
        <div class="kd dimc">gross retention</div>
      </div>
      <div class="card kpi">
        <div class="kk">Avg ACV</div>
        <div class="kv">${{ Math.round(arr / plans.reduce((s, p) => s + p.accts, 0)).toLocaleString() }}</div>
        <div class="kd dimc">across {{ plans.reduce((s, p) => s + p.accts, 0) }} accounts</div>
      </div>
      <div class="card kpi">
        <div class="kk">LTV · estimate</div>
        <div class="kv">$84.2k</div>
        <div class="kd up">payback 7.2 mo</div>
      </div>
    </div>

    <div class="card">
      <h3>MRR movement · waterfall</h3>
      <p class="meta">${{ Math.round(lastMrr / 1000) }}k → ${{ Math.round(mrr / 1000) }}k this month.</p>
      <div class="wf-wrap">
        <div class="wf">
          <div v-for="(w, i) in waterfallPos" :key="i" class="wb">
            <div class="wb-amt" :class="w.kind">{{ w.label }}</div>
            <div class="wb-col">
              <div class="wb-bar" :class="w.kind" :style="{ height: w.height + '%', bottom: w.bottom + '%' }"></div>
            </div>
            <div class="wb-lbl">{{ w.k }}</div>
          </div>
        </div>
      </div>
      <div class="legend">
        <span><span class="lg start"></span>Starting / Ending</span>
        <span><span class="lg pos"></span>Adds</span>
        <span><span class="lg neg"></span>Losses</span>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>Revenue by plan</h3>
        <div class="plans">
          <div v-for="p in plans" :key="p.name" class="pl">
            <div class="pl-head">
              <span class="pl-name"><span class="pl-dot" :style="{ background: p.color }"></span>{{ p.name }}</span>
              <span class="pl-meta">{{ p.accts }} accts</span>
            </div>
            <div class="pl-bar">
              <div class="pl-fill" :style="{ width: (p.mrr / totalMrr * 100) + '%', background: p.color }"></div>
            </div>
            <div class="pl-foot">
              <span class="pl-num">${{ Math.round(p.mrr / 1000) }}k MRR</span>
              <span class="dimc-i">{{ Math.round(p.mrr / totalMrr * 100) }}%</span>
              <span class="pl-arpu">$${{ Math.round(p.mrr / p.accts) }} ARPU</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Cohort NRR · trailing</h3>
        <p class="meta">Expansion index 100 = no change from cohort starting MRR.</p>
        <div class="ch">
          <div v-for="c in cohorts" :key="c.quarter" class="ch-row">
            <span class="ch-q">{{ c.quarter }}</span>
            <span class="ch-size">{{ c.retained }} / {{ c.size }} kept</span>
            <div class="ch-bar">
              <div class="ch-100"></div>
              <div class="ch-fill" :class="c.expansion >= 100 ? 'pos' : 'neg'" :style="{ width: Math.min(150, c.expansion) / 1.5 + '%' }"></div>
            </div>
            <span class="ch-val" :class="c.expansion >= 100 ? 'pos' : 'neg'">{{ c.expansion }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rd { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.dimc-i { color: var(--text-dim); font-size: 11px; }

.kpi-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
.kpi { padding: 16px 18px; }
.kk { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.kv { font-size: 24px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; margin: 8px 0 4px; }
.kv.up { color: var(--success); }
.kd { font-size: 11px; }
.kd.up { color: var(--success); }
.kd.dimc { color: var(--text-dim); }

.wf-wrap { padding: 14px 0; }
.wf { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; height: 240px; align-items: end; }
.wb { display: flex; flex-direction: column; align-items: center; gap: 6px; height: 100%; position: relative; }
.wb-amt { font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums; min-height: 14px; }
.wb-amt.pos { color: var(--success); }
.wb-amt.neg { color: var(--danger); }
.wb-amt.start, .wb-amt.end { color: var(--text); }
.wb-col { width: 100%; flex: 1; position: relative; }
.wb-bar { position: absolute; left: 10%; right: 10%; border-radius: 4px; min-height: 6px; }
.wb-bar.start { background: var(--text-dim); }
.wb-bar.end { background: linear-gradient(180deg, var(--primary), var(--primary-2)); }
.wb-bar.pos { background: var(--success); }
.wb-bar.neg { background: var(--danger); }
.wb-lbl { font-size: 10px; color: var(--text-dim); text-align: center; }

.legend { display: flex; gap: 16px; padding-top: 14px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-dim); margin-top: 14px; flex-wrap: wrap; }
.lg { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }
.lg.start { background: var(--text-dim); }
.lg.pos { background: var(--success); }
.lg.neg { background: var(--danger); }

.row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.plans { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.pl { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.pl-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.pl-name { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13px; }
.pl-dot { width: 10px; height: 10px; border-radius: 50%; }
.pl-meta { font-size: 11px; color: var(--text-dim); }
.pl-bar { height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-bottom: 6px; }
.pl-fill { height: 100%; }
.pl-foot { display: flex; gap: 10px; align-items: center; font-size: 12px; }
.pl-num { font-weight: 700; font-variant-numeric: tabular-nums; }
.pl-arpu { margin-left: auto; color: var(--text-dim); font-variant-numeric: tabular-nums; }

.ch { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.ch-row { display: grid; grid-template-columns: 80px 80px 1fr 50px; gap: 12px; align-items: center; font-size: 13px; }
.ch-q { font-weight: 700; }
.ch-size { color: var(--text-dim); font-size: 11px; }
.ch-bar { position: relative; height: 10px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.ch-100 { position: absolute; top: -2px; bottom: -2px; left: calc(100% / 1.5); width: 1.5px; background: var(--text-dim); opacity: .5; }
.ch-fill { height: 100%; border-radius: 999px; }
.ch-fill.pos { background: linear-gradient(90deg, var(--primary-2), var(--success)); }
.ch-fill.neg { background: var(--danger); }
.ch-val { font-weight: 800; font-variant-numeric: tabular-nums; text-align: right; }
.ch-val.pos { color: var(--success); }
.ch-val.neg { color: var(--danger); }

@media (max-width: 1024px) {
  .kpi-row { grid-template-columns: repeat(3, 1fr); }
  .row { grid-template-columns: 1fr; }
  .wf { font-size: 10px; }
}
@media (max-width: 540px) {
  .kpi-row { grid-template-columns: 1fr 1fr; }
}
</style>
