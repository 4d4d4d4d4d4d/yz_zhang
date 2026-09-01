<script setup>
import { computed } from 'vue'
import { forecastSummary, DEFAULT_STAGES, COVERAGE_BENCHMARK } from '../logic/salesForecast.js'

const quarter = 'Q4 FY26'
const quota = 4200000

// Spec 47 — weights come from the shared ladder; displayed high→low so the
// funnel reads in order (the inline list had Proposal above Negotiation).
const STAGE_COLOR = {
  'Closed Won': '#34d399', Verbal: '#22d3ee', Negotiation: '#a78bfa',
  Proposal: '#7c5cff', Discovery: '#fbbf24', Lead: '#94a3b8'
}
const stages = [...DEFAULT_STAGES].reverse().map(s => ({ ...s, color: STAGE_COLOR[s.name] }))

const deals = [
  { id: 'D-2841', name: 'Lumen Studios · JP',    stage: 'Negotiation', value: 840000, owner: 'AM', category: 'best',   close: 'Dec 18' },
  { id: 'D-2842', name: 'Northwave · LATAM',     stage: 'Closed Won',  value: 1200000, owner: 'AM', category: 'commit', close: 'Nov 24' },
  { id: 'D-2843', name: 'Aurora Media · APAC',   stage: 'Verbal',      value: 620000, owner: 'KT', category: 'commit', close: 'Dec 12' },
  { id: 'D-2844', name: 'Nimbus Labs · US',      stage: 'Proposal',    value: 980000, owner: 'AM', category: 'best',   close: 'Dec 28' },
  { id: 'D-2845', name: 'Cobalt Legal · EU',     stage: 'Negotiation', value: 220000, owner: 'KT', category: 'commit', close: 'Dec 14' },
  { id: 'D-2846', name: 'Verda Commerce · SG',   stage: 'Discovery',   value: 540000, owner: 'KT', category: 'upside', close: 'Jan 18' },
  { id: 'D-2847', name: 'Solace Studio · KR',    stage: 'Lead',        value: 140000, owner: 'HM', category: 'upside', close: 'Jan 22' },
  { id: 'D-2848', name: 'Mizu Logistics · JP',   stage: 'Proposal',    value: 380000, owner: 'HM', category: 'best',   close: 'Dec 30' },
  { id: 'D-2849', name: 'Helio Network · BR',    stage: 'Discovery',   value:  95000, owner: 'AM', category: 'upside', close: 'Jan 12' }
]

// Spec 47 — all roll-ups come from the audited forecast engine. Categories are
// a partition: commit already contains Closed Won, so it is never re-added.
const fc = computed(() => forecastSummary({ deals, quota }))

const weighted = computed(() => fc.value.weighted)
const commit = computed(() => fc.value.commit)
const best = computed(() => fc.value.best)
const upside = computed(() => fc.value.upside)

const stageTotals = computed(() => stages.map(s => ({
  ...s,
  total: deals.filter(d => d.stage === s.name).reduce((sum, d) => sum + d.value, 0),
  weighted: deals.filter(d => d.stage === s.name).reduce((sum, d) => sum + d.value * s.weight, 0),
  count: deals.filter(d => d.stage === s.name).length
})))

const closedWon = computed(() => fc.value.closedWon)
const attainment = computed(() => Math.round(fc.value.attainment))
const gap = computed(() => fc.value.gap)
// Commit beyond what is already banked — used to stack the attainment bar
// without painting the Closed Won segment twice.
const commitOpen = computed(() => Math.max(0, fc.value.committed - fc.value.closedWon))
</script>

<template>
  <div class="fcs">
    <div class="card head">
      <div>
        <div class="kicker">Forecast · {{ quarter }}</div>
        <h3>${{ Math.round(weighted / 1000).toLocaleString() }}k weighted pipeline</h3>
        <p class="meta">Quota ${{ (quota / 1000).toLocaleString() }}k · gap to quota ${{ Math.round(gap / 1000).toLocaleString() }}k</p>
        <p class="cov" :class="fc.coverageHealthy ? 'ok' : 'warn'">
          Pipeline coverage
          <strong>{{ fc.coverage === null ? '—' : fc.coverage.toFixed(1) + '×' }}</strong>
          <span class="cov-bm">vs {{ COVERAGE_BENCHMARK }}× benchmark · ${{ Math.round(fc.openPipeline / 1000).toLocaleString() }}k open</span>
        </p>
      </div>
      <div class="att">
        <div class="att-bar">
          <div class="att-fill won" :style="{ width: (closedWon / quota * 100) + '%' }" :title="`Closed Won · $${Math.round(closedWon/1000)}k`"></div>
          <div class="att-fill commit" :style="{ width: (commitOpen / quota * 100) + '%' }" :title="`Commit (open) · $${Math.round(commitOpen/1000)}k`"></div>
          <div class="att-fill best" :style="{ width: (best / quota * 100) + '%' }" :title="`Best case · $${Math.round(best/1000)}k`"></div>
        </div>
        <div class="att-num grad-text">{{ attainment }}%</div>
        <div class="att-lbl">of quota committed</div>
      </div>
    </div>

    <div class="cat-row">
      <div class="card cat won">
        <div class="cat-lbl">Closed Won</div>
        <div class="cat-num">${{ Math.round(closedWon / 1000).toLocaleString() }}k</div>
        <div class="cat-meta">{{ deals.filter(d => d.stage === 'Closed Won').length }} deals · 100% probability</div>
      </div>
      <div class="card cat commit">
        <div class="cat-lbl">Commit</div>
        <div class="cat-num">${{ Math.round(commit / 1000).toLocaleString() }}k</div>
        <div class="cat-meta">{{ deals.filter(d => d.category === 'commit').length }} deals · 85% probability</div>
      </div>
      <div class="card cat best">
        <div class="cat-lbl">Best case</div>
        <div class="cat-num">${{ Math.round(best / 1000).toLocaleString() }}k</div>
        <div class="cat-meta">{{ deals.filter(d => d.category === 'best').length }} deals · 50% probability</div>
      </div>
      <div class="card cat upside">
        <div class="cat-lbl">Upside</div>
        <div class="cat-num">${{ Math.round(upside / 1000).toLocaleString() }}k</div>
        <div class="cat-meta">{{ deals.filter(d => d.category === 'upside').length }} deals · 20% probability</div>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>By stage</h3>
        <p class="meta">Weighted using stage probability.</p>
        <div class="stages">
          <div v-for="s in stageTotals" :key="s.name" class="stage">
            <div class="s-head">
              <span class="s-name"><span class="s-dot" :style="{ background: s.color }"></span>{{ s.name }}</span>
              <span class="s-meta">{{ s.count }} deals · {{ Math.round(s.weight * 100) }}%</span>
            </div>
            <div class="s-bar">
              <div class="s-total" :style="{ width: (s.total / quota * 100 * 1.2) + '%', background: s.color, opacity: .25 }"></div>
              <div class="s-weighted" :style="{ width: (s.weighted / quota * 100 * 1.2) + '%', background: s.color }"></div>
            </div>
            <div class="s-num">
              <span>${{ Math.round(s.total / 1000) }}k raw</span>
              <span class="dimc-i">·</span>
              <span class="strong">${{ Math.round(s.weighted / 1000) }}k weighted</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Top deals · {{ quarter }}</h3>
        <table class="td">
          <thead>
            <tr><th>Deal</th><th>Stage</th><th class="num">Value</th><th>Close</th></tr>
          </thead>
          <tbody>
            <tr v-for="d in [...deals].sort((a,b)=>b.value-a.value).slice(0,6)" :key="d.id">
              <td>
                <div class="td-name">{{ d.name }}</div>
                <div class="td-meta">{{ d.id }} · {{ d.owner }} · <span class="cat-pill" :class="d.category">{{ d.category }}</span></div>
              </td>
              <td><span class="st-pill">{{ d.stage }}</span></td>
              <td class="num">${{ Math.round(d.value / 1000) }}k</td>
              <td class="dimc-i">{{ d.close }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fcs { display: flex; flex-direction: column; gap: 16px; }
.cov { font-size: 12px; margin: 8px 0 0; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.cov strong { font-size: 15px; font-variant-numeric: tabular-nums; }
.cov.ok strong { color: var(--success); }
.cov.warn strong { color: #fbbf24; }
.cov-bm { color: var(--text-dim); }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.att { text-align: right; }
.att-bar { display: flex; height: 18px; border-radius: 10px; overflow: hidden; border: 1px solid var(--border); width: 280px; margin-left: auto; }
.att-fill { height: 100%; }
.att-fill.won { background: var(--success); }
.att-fill.commit { background: var(--primary); }
.att-fill.best { background: rgba(124, 92, 255, .4); }
.att-num { font-size: 28px; font-weight: 800; line-height: 1; margin-top: 8px; }
.att-lbl { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 2px; }

.cat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.cat { padding: 16px 18px; border-left: 3px solid; }
.cat.won { border-color: var(--success); }
.cat.commit { border-color: var(--primary); }
.cat.best { border-color: rgba(124, 92, 255, .5); }
.cat.upside { border-color: #fcd34d; }
.cat-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.cat-num { font-size: 26px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; margin: 4px 0 4px; }
.cat-meta { font-size: 11px; color: var(--text-dim); }

.row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.stages { display: flex; flex-direction: column; gap: 12px; margin-top: 14px; }
.stage { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.s-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.s-name { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13px; }
.s-dot { width: 10px; height: 10px; border-radius: 50%; }
.s-meta { font-size: 11px; color: var(--text-dim); }
.s-bar { position: relative; height: 8px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-bottom: 6px; }
.s-total { position: absolute; left: 0; top: 0; height: 100%; border-radius: 999px; }
.s-weighted { position: absolute; left: 0; top: 0; height: 100%; border-radius: 999px; }
.s-num { display: flex; gap: 8px; align-items: center; font-size: 11px; color: var(--text-dim); }
.s-num .strong { color: var(--text); font-weight: 700; }
.dimc-i { color: var(--text-dim); }

.td { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 12px; }
.td th { text-align: left; padding: 8px 10px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.td th.num { text-align: right; }
.td td { padding: 10px; border-bottom: 1px dashed var(--border); }
.td td.num { text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; }
.td-name { font-weight: 600; font-size: 13px; }
.td-meta { font-size: 11px; color: var(--text-dim); margin-top: 2px; display: flex; gap: 6px; align-items: center; }
.cat-pill { padding: 1px 7px; border-radius: 4px; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.cat-pill.commit { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.cat-pill.best { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.cat-pill.upside { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.st-pill { padding: 2px 8px; border-radius: 5px; background: var(--surface-2); font-size: 11px; }

@media (max-width: 1024px) {
  .cat-row { grid-template-columns: 1fr 1fr; }
  .row { grid-template-columns: 1fr; }
  .att-bar { width: 220px; }
}
</style>
