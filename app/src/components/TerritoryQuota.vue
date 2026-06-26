<script setup>
import { computed } from 'vue'

const reps = [
  { id: 'AM', name: 'Akiko Mori',     territory: 'JP / KR',    quota: 1200000, closed: 982000,  pipeline: 1840000, accounts: 142, icp: 86 },
  { id: 'KT', name: 'Kenji Tanaka',   territory: 'APAC ex-JP', quota: 1100000, closed: 1240000, pipeline: 1620000, accounts: 168, icp: 78 },
  { id: 'HM', name: 'Hana Mizuno',    territory: 'LATAM',      quota:  900000, closed:  540000, pipeline: 1180000, accounts:  98, icp: 62 },
  { id: 'DR', name: 'Diego Ramos',    territory: 'EMEA',       quota: 1000000, closed:  784000, pipeline: 1340000, accounts: 114, icp: 71 }
]

const totals = computed(() => ({
  quota:    reps.reduce((s, r) => s + r.quota, 0),
  closed:   reps.reduce((s, r) => s + r.closed, 0),
  pipeline: reps.reduce((s, r) => s + r.pipeline, 0),
  accounts: reps.reduce((s, r) => s + r.accounts, 0)
}))

const heatmap = [
  { name: 'Beauty',  JP: 92, KR: 88, APAC: 74, LATAM: 52, EMEA: 64 },
  { name: 'Fashion', JP: 78, KR: 82, APAC: 71, LATAM: 68, EMEA: 80 },
  { name: 'SaaS',    JP: 56, KR: 48, APAC: 62, LATAM: 71, EMEA: 84 },
  { name: 'Food',    JP: 64, KR: 58, APAC: 76, LATAM: 88, EMEA: 52 },
  { name: 'Tech',    JP: 70, KR: 76, APAC: 68, LATAM: 60, EMEA: 78 }
]
const territories = ['JP', 'KR', 'APAC', 'LATAM', 'EMEA']

function attainmentClass(pct) {
  if (pct >= 110) return 'over'
  if (pct >= 85) return 'on'
  if (pct >= 60) return 'mid'
  return 'risk'
}
function cell(v) {
  if (v >= 80) return 'h-90'
  if (v >= 65) return 'h-75'
  if (v >= 50) return 'h-55'
  return 'h-35'
}
</script>

<template>
  <div class="tq">
    <div class="card head">
      <div>
        <div class="kicker">Territory & quota · {{ reps.length }} reps · 5 territories</div>
        <h3>${{ Math.round(totals.closed / 1000).toLocaleString() }}k closed · ${{ Math.round(totals.pipeline / 1000).toLocaleString() }}k open pipeline</h3>
        <p class="meta">Quarterly attainment {{ Math.round(totals.closed / totals.quota * 100) }}% of ${{ Math.round(totals.quota / 1000).toLocaleString() }}k quota.</p>
      </div>
      <div class="kpis">
        <div><div class="kn grad-text">{{ Math.round(totals.closed / totals.quota * 100) }}%</div><div class="kl">Avg attainment</div></div>
        <div><div class="kn">{{ totals.accounts.toLocaleString() }}</div><div class="kl">Accounts</div></div>
      </div>
    </div>

    <div class="card">
      <h3>Rep performance</h3>
      <table class="rt">
        <thead>
          <tr>
            <th>Rep · Territory</th>
            <th class="num">Quota</th>
            <th class="num">Closed</th>
            <th>Attainment</th>
            <th class="num">Pipeline</th>
            <th class="num">Coverage</th>
            <th class="num">ICP %</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in reps" :key="r.id">
            <td>
              <div class="rep">
                <div class="r-av">{{ r.id }}</div>
                <div>
                  <div class="r-name">{{ r.name }}</div>
                  <div class="r-terr">{{ r.territory }} · {{ r.accounts }} accts</div>
                </div>
              </div>
            </td>
            <td class="num">${{ Math.round(r.quota / 1000) }}k</td>
            <td class="num">${{ Math.round(r.closed / 1000) }}k</td>
            <td>
              <div class="att-row">
                <div class="att-bar">
                  <div class="att-fill" :class="attainmentClass(r.closed / r.quota * 100)" :style="{ width: Math.min(120, r.closed / r.quota * 100) + '%' }"></div>
                  <div class="att-100"></div>
                </div>
                <span class="att-num" :class="attainmentClass(r.closed / r.quota * 100)">{{ Math.round(r.closed / r.quota * 100) }}%</span>
              </div>
            </td>
            <td class="num">${{ Math.round(r.pipeline / 1000) }}k</td>
            <td class="num">{{ ((r.closed + r.pipeline) / r.quota).toFixed(1) }}×</td>
            <td class="num"><span class="icp-pill" :class="r.icp >= 80 ? 'ok' : r.icp >= 65 ? 'warn' : 'risk'">{{ r.icp }}%</span></td>
            <td>
              <span class="st-pill" :class="attainmentClass(r.closed / r.quota * 100)">
                {{ attainmentClass(r.closed / r.quota * 100) === 'over' ? 'Over plan' :
                   attainmentClass(r.closed / r.quota * 100) === 'on' ? 'On track' :
                   attainmentClass(r.closed / r.quota * 100) === 'mid' ? 'Behind' : 'At risk' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>ICP coverage · category × territory</h3>
      <p class="meta">% of identified ICP accounts already engaged. Hot zones = expansion opportunities.</p>
      <div class="hm">
        <div class="hh">
          <span></span>
          <span v-for="t in territories" :key="t" class="hh-c">{{ t }}</span>
        </div>
        <div v-for="row in heatmap" :key="row.name" class="hr">
          <span class="hr-lbl">{{ row.name }}</span>
          <span v-for="t in territories" :key="t" class="hc" :class="cell(row[t])">{{ row[t] }}</span>
        </div>
      </div>
      <div class="leg">
        <span><span class="lc h-35"></span>&lt;50%</span>
        <span><span class="lc h-55"></span>50–64%</span>
        <span><span class="lc h-75"></span>65–79%</span>
        <span><span class="lc h-90"></span>≥80%</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tq { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.kpis { display: flex; gap: 20px; }
.kn { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.kl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.rt { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }
.rt th { text-align: left; padding: 10px 8px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.rt th.num { text-align: right; }
.rt td { padding: 14px 8px; border-bottom: 1px dashed var(--border); }
.rt td.num { text-align: right; font-variant-numeric: tabular-nums; }

.rep { display: flex; gap: 10px; align-items: center; }
.r-av { width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; display: grid; place-items: center; font-weight: 800; font-size: 11px; }
.r-name { font-weight: 600; font-size: 13px; }
.r-terr { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

.att-row { display: flex; align-items: center; gap: 10px; }
.att-bar { position: relative; flex: 1; height: 8px; background: var(--surface-2); border-radius: 999px; overflow: hidden; min-width: 120px; }
.att-fill { height: 100%; border-radius: 999px; }
.att-fill.over { background: var(--success); }
.att-fill.on { background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.att-fill.mid { background: #fcd34d; }
.att-fill.risk { background: var(--danger); }
.att-100 { position: absolute; top: 0; left: calc(100% / 1.2); bottom: 0; width: 1px; background: var(--text-dim); opacity: .4; }
.att-num { font-weight: 800; font-variant-numeric: tabular-nums; font-size: 12px; min-width: 44px; text-align: right; }
.att-num.over { color: var(--success); }
.att-num.on { color: var(--primary-2); }
.att-num.mid { color: #fcd34d; }
.att-num.risk { color: var(--danger); }

.icp-pill { padding: 2px 8px; border-radius: 5px; font-weight: 700; font-size: 11px; }
.icp-pill.ok { background: rgba(52, 211, 153, .12); color: #6ee7b7; }
.icp-pill.warn { background: rgba(251, 191, 36, .12); color: #fcd34d; }
.icp-pill.risk { background: rgba(248, 113, 113, .12); color: #fca5a5; }

.st-pill { font-size: 10px; padding: 3px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.st-pill.over { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.st-pill.on { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.st-pill.mid { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.st-pill.risk { background: rgba(248, 113, 113, .15); color: #fca5a5; }

.hm { display: flex; flex-direction: column; gap: 4px; margin-top: 14px; overflow-x: auto; }
.hh { display: grid; grid-template-columns: 100px repeat(5, 1fr); gap: 4px; }
.hh-c { text-align: center; padding: 6px 0; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; font-weight: 700; }
.hr { display: grid; grid-template-columns: 100px repeat(5, 1fr); gap: 4px; }
.hr-lbl { padding: 8px 10px; font-size: 13px; font-weight: 600; align-self: center; }
.hc { display: grid; place-items: center; aspect-ratio: 2 / 1; border-radius: 6px; color: #fff; font-variant-numeric: tabular-nums; font-weight: 600; font-size: 13px; min-height: 32px; }
.h-35 { background: #c4b5fd; color: #1a1a2e; }
.h-55 { background: #7c5cff; }
.h-75 { background: #4f46e5; }
.h-90 { background: #2563eb; }

.leg { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-dim); }
.lc { display: inline-block; width: 14px; height: 14px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }

@media (max-width: 1024px) {
  .rt th:nth-child(5), .rt td:nth-child(5),
  .rt th:nth-child(6), .rt td:nth-child(6) { display: none; }
  .hm { min-width: 500px; }
}
</style>
