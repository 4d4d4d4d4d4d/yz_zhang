<script setup>
import { computed } from 'vue'

const kpis = [
  { k: 'Avg time-to-close', v: '17.4 d', d: '−4.2d',  up: true },
  { k: 'Avg redlines / deal', v: '11.6', d: '−2.8',    up: true },
  { k: 'Avg approvers', v: '3.2',         d: '+0.4',    up: false },
  { k: 'Win rate', v: '78%',               d: '+6pt',    up: true },
  { k: 'AI suggested · accepted', v: '64%', d: '+12pt',  up: true },
  { k: 'NDA → MSA conversion', v: '52%',    d: '+8pt',   up: true }
]

const clauses = [
  { name: 'Exclusivity',      redlines: 84, accept: 28, ai_accept: 64, avg_rounds: 3.2, value_band: 'high' },
  { name: 'Pricing / Rebate', redlines: 142, accept: 52, ai_accept: 78, avg_rounds: 2.8, value_band: 'high' },
  { name: 'Term / Renewal',   redlines: 96, accept: 38, ai_accept: 71, avg_rounds: 2.4, value_band: 'med' },
  { name: 'IP indemnity',     redlines: 72, accept: 62, ai_accept: 84, avg_rounds: 1.8, value_band: 'med' },
  { name: 'Data / Privacy',   redlines: 58, accept: 88, ai_accept: 92, avg_rounds: 1.4, value_band: 'low' },
  { name: 'Liability cap',    redlines: 66, accept: 74, ai_accept: 86, avg_rounds: 1.6, value_band: 'med' },
  { name: 'Confidentiality',  redlines: 22, accept: 96, ai_accept: 98, avg_rounds: 1.1, value_band: 'low' },
  { name: 'AI provenance',    redlines: 41, accept: 78, ai_accept: 88, avg_rounds: 1.5, value_band: 'med' }
]

const ttc = [
  { band: '< $50K',    deals: 84, days: 8.2,  win: 92, color: '#34d399' },
  { band: '$50–250K',  deals: 142, days: 14.8, win: 84, color: '#22d3ee' },
  { band: '$250K–1M',  deals: 68,  days: 22.4, win: 74, color: '#7c5cff' },
  { band: '> $1M',     deals: 24,  days: 38.6, win: 62, color: '#ff7ad9' }
]

function heat(v, max) {
  const p = v / max
  if (p >= 0.75) return 'h-3'
  if (p >= 0.5) return 'h-2'
  if (p >= 0.25) return 'h-1'
  return 'h-0'
}
const maxRed = computed(() => Math.max(...clauses.map(c => c.redlines)))
</script>

<template>
  <div class="ca">
    <div class="card head">
      <div>
        <div class="kicker">CLM analytics · last 90 days</div>
        <h3>318 contracts · ${{ (38.4).toFixed(1) }}M total value</h3>
        <p class="meta">AI is reducing time-to-close and redline volume — accepted suggestions up 12pt QoQ.</p>
      </div>
    </div>

    <div class="kpi-grid">
      <div v-for="k in kpis" :key="k.k" class="card kpi">
        <div class="kk">{{ k.k }}</div>
        <div class="kv">{{ k.v }}</div>
        <div class="kd" :class="k.up ? 'up' : 'down'">{{ k.up ? '▲' : '▼' }} {{ k.d }}</div>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>Hot clauses · redline frequency</h3>
        <p class="meta">Where most negotiation time is spent. AI fallback accept-rate in green.</p>
        <table class="ct">
          <thead>
            <tr>
              <th>Clause</th>
              <th class="num">Redlines</th>
              <th>Heat</th>
              <th class="num">Direct accept</th>
              <th class="num">AI accept</th>
              <th class="num">Rounds</th>
              <th>Band</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in clauses" :key="c.name">
              <td>{{ c.name }}</td>
              <td class="num">{{ c.redlines }}</td>
              <td>
                <div class="hbar">
                  <div class="hfill" :class="heat(c.redlines, maxRed)" :style="{ width: (c.redlines / maxRed * 100) + '%' }"></div>
                </div>
              </td>
              <td class="num">{{ c.accept }}%</td>
              <td class="num"><span class="ai-pill" :class="c.ai_accept >= 80 ? 'high' : c.ai_accept >= 60 ? 'med' : 'low'">{{ c.ai_accept }}%</span></td>
              <td class="num">{{ c.avg_rounds }}</td>
              <td><span class="band" :class="c.value_band">{{ c.value_band }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>Time-to-close by value band</h3>
        <p class="meta">Larger deals take longer but show higher willingness to accept AI suggestions.</p>
        <div class="bands">
          <div v-for="b in ttc" :key="b.band" class="b">
            <div class="b-head">
              <span class="b-name"><span class="b-dot" :style="{ background: b.color }"></span>{{ b.band }}</span>
              <span class="b-meta">{{ b.deals }} deals · {{ b.win }}% win</span>
            </div>
            <div class="b-row">
              <div class="b-bar">
                <div class="b-fill" :style="{ width: (b.days / 40 * 100) + '%', background: b.color }"></div>
              </div>
              <span class="b-num">{{ b.days }}d</span>
            </div>
          </div>
        </div>

        <div class="insight">
          <span class="ai-tag">AI</span>
          Bottleneck: <strong>$250K–1M</strong> band. Pricing &amp; Exclusivity drive +9 days vs target. Switching to fallback-2 on Pricing would cut median by 5 days.
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ca { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.kpi-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
.kpi { padding: 16px 18px; }
.kk { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.kv { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; margin: 6px 0 4px; }
.kd { font-size: 11px; }
.kd.up { color: var(--success); }
.kd.down { color: var(--danger); }

.row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }

.ct { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 12px; }
.ct th { text-align: left; padding: 8px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.ct th.num { text-align: right; }
.ct td { padding: 10px 8px; border-bottom: 1px dashed var(--border); }
.ct td.num { text-align: right; font-variant-numeric: tabular-nums; }

.hbar { height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; min-width: 80px; }
.hfill { height: 100%; border-radius: 999px; }
.hfill.h-0 { background: rgba(34, 211, 238, .5); }
.hfill.h-1 { background: rgba(124, 92, 255, .6); }
.hfill.h-2 { background: rgba(251, 191, 36, .7); }
.hfill.h-3 { background: rgba(248, 113, 113, .8); }

.ai-pill { padding: 2px 8px; border-radius: 5px; font-weight: 700; font-size: 11px; }
.ai-pill.high { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.ai-pill.med { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.ai-pill.low { background: rgba(96, 165, 250, .15); color: #93c5fd; }

.band { font-size: 10px; padding: 2px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.band.high { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.band.med { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.band.low { background: rgba(52, 211, 153, .15); color: #6ee7b7; }

.bands { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.b { padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.b-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.b-name { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13px; }
.b-dot { width: 10px; height: 10px; border-radius: 50%; }
.b-meta { font-size: 11px; color: var(--text-dim); }
.b-row { display: flex; align-items: center; gap: 12px; }
.b-bar { flex: 1; height: 8px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.b-fill { height: 100%; border-radius: 999px; }
.b-num { font-variant-numeric: tabular-nums; font-weight: 700; font-size: 13px; min-width: 40px; text-align: right; }

.insight { display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; background: rgba(124, 92, 255, .08); border: 1px solid rgba(124, 92, 255, .25); border-radius: 10px; font-size: 12px; color: var(--text-dim); margin-top: 16px; line-height: 1.5; }
.insight strong { color: var(--text); }
.ai-tag { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 800; letter-spacing: .05em; flex-shrink: 0; }

@media (max-width: 1024px) {
  .kpi-grid { grid-template-columns: repeat(3, 1fr); }
  .row { grid-template-columns: 1fr; }
}
@media (max-width: 540px) {
  .kpi-grid { grid-template-columns: 1fr 1fr; }
}
</style>
