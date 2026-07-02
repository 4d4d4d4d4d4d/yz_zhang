<script setup>
import { ref, computed } from 'vue'

const accounts = ref([
  { name: 'Lumen Studios',      mrr: 9800,  csm: 'Akiko',   signals: { usage: 92, payment: 100, support: 88, adoption: 84, sentiment: 92 }, renewalIn: 172, trend: 'up' },
  { name: 'Northwave Partners', mrr: 12400, csm: 'Akiko',   signals: { usage: 74, payment: 100, support: 82, adoption: 68, sentiment: 78 }, renewalIn: 68,  trend: 'flat' },
  { name: 'Aurora Media',       mrr: 6200,  csm: 'Kenji',   signals: { usage: 88, payment: 92,  support: 84, adoption: 76, sentiment: 84 }, renewalIn: 240, trend: 'up' },
  { name: 'Kaito Beauty',       mrr: 2400,  csm: 'Hana',    signals: { usage: 96, payment: 100, support: 76, adoption: 82, sentiment: 88 }, renewalIn: 316, trend: 'up' },
  { name: 'Cobalt Legal',       mrr: 1800,  csm: 'Diego',   signals: { usage: 62, payment: 100, support: 72, adoption: 58, sentiment: 62 }, renewalIn: 124, trend: 'down' },
  { name: 'Mizu Logistics',     mrr:  980,  csm: 'Hana',    signals: { usage: 38, payment: 68,  support: 52, adoption: 34, sentiment: 42 }, renewalIn: 42,  trend: 'down' },
  { name: 'Helio Network',      mrr:  420,  csm: 'Diego',   signals: { usage: 54, payment: 100, support: 68, adoption: 48, sentiment: 62 }, renewalIn: 220, trend: 'flat' },
  { name: 'Verda Commerce',     mrr:  380,  csm: 'Hana',    signals: { usage: 82, payment: 100, support: 92, adoption: 76, sentiment: 84 }, renewalIn: 96,  trend: 'up' }
])

const weights = { usage: 0.3, payment: 0.15, support: 0.15, adoption: 0.25, sentiment: 0.15 }

function score(a) {
  let s = 0
  for (const k in weights) s += a.signals[k] * weights[k]
  return Math.round(s)
}
function band(s) {
  if (s >= 80) return 'ok'
  if (s >= 60) return 'warn'
  return 'risk'
}
function churnProb(s, renewalIn) {
  const base = Math.max(0, 100 - s) / 100
  const urgency = Math.max(0, (120 - renewalIn) / 120)
  return Math.round((base * 0.7 + urgency * 0.3) * 100)
}

const enriched = computed(() => accounts.value.map(a => ({
  ...a,
  score: score(a),
  band: band(score(a)),
  churn: churnProb(score(a), a.renewalIn)
})).sort((a, b) => a.score - b.score))

const summary = computed(() => ({
  total: accounts.value.length,
  ok: enriched.value.filter(a => a.band === 'ok').length,
  warn: enriched.value.filter(a => a.band === 'warn').length,
  risk: enriched.value.filter(a => a.band === 'risk').length,
  mrrAtRisk: enriched.value.filter(a => a.band === 'risk').reduce((s, a) => s + a.mrr, 0),
  avgScore: Math.round(enriched.value.reduce((s, a) => s + a.score, 0) / enriched.value.length)
}))

const selected = ref(enriched.value[0]?.name)
const cur = computed(() => enriched.value.find(a => a.name === selected.value))
</script>

<template>
  <div class="ch">
    <div class="card head">
      <div>
        <div class="kicker">Customer health · composite score</div>
        <h3>{{ summary.total }} accounts · avg score {{ summary.avgScore }}</h3>
        <p class="meta">Weighted: usage 30% · adoption 25% · payment 15% · support 15% · sentiment 15%. Score recomputed nightly from feature-store signals.</p>
      </div>
    </div>

    <div class="kpi-row">
      <div class="card kpi ok">
        <div class="cn">{{ summary.ok }}</div>
        <div class="cl">Healthy · ≥80</div>
      </div>
      <div class="card kpi warn">
        <div class="cn">{{ summary.warn }}</div>
        <div class="cl">Watch · 60–79</div>
      </div>
      <div class="card kpi risk">
        <div class="cn">{{ summary.risk }}</div>
        <div class="cl">At risk · &lt;60</div>
      </div>
      <div class="card kpi">
        <div class="cn danger">${{ summary.mrrAtRisk.toLocaleString() }}</div>
        <div class="cl">MRR at risk</div>
      </div>
    </div>

    <div class="grid">
      <div class="card list">
        <div v-for="a in enriched" :key="a.name"
          class="ac" :class="[a.band, { on: selected === a.name }]"
          @click="selected = a.name">
          <div class="ac-top">
            <span class="ac-name">{{ a.name }}</span>
            <span class="ac-score" :class="a.band">{{ a.score }}</span>
          </div>
          <div class="ac-meta">
            <span>${{ a.mrr.toLocaleString() }}/mo</span>
            <span class="dot">·</span>
            <span>renewal in {{ a.renewalIn }}d</span>
            <span class="dot">·</span>
            <span class="trend" :class="a.trend">{{ a.trend === 'up' ? '▲' : a.trend === 'down' ? '▼' : '—' }} {{ a.trend }}</span>
          </div>
        </div>
      </div>

      <div class="card detail">
        <div class="d-head">
          <div>
            <div class="kicker">CSM · {{ cur.csm }}</div>
            <h3>{{ cur.name }}</h3>
            <p class="meta">${{ cur.mrr.toLocaleString() }}/mo · renewal in {{ cur.renewalIn }} days</p>
          </div>
          <div class="d-right">
            <div class="d-score" :class="cur.band">
              <div class="ds-num">{{ cur.score }}</div>
              <div class="ds-lbl">Health</div>
            </div>
            <div class="d-churn">
              <div class="dc-num">{{ cur.churn }}%</div>
              <div class="dc-lbl">Churn risk</div>
            </div>
          </div>
        </div>

        <div class="kicker">Signal breakdown</div>
        <div class="signals">
          <div v-for="(v, k) in cur.signals" :key="k" class="sg">
            <div class="sg-head">
              <span class="sg-k">{{ k }} <span class="dimc-i">· weight {{ Math.round(weights[k] * 100) }}%</span></span>
              <span class="sg-v" :class="band(v)">{{ v }}</span>
            </div>
            <div class="sg-bar">
              <div class="sg-fill" :class="band(v)" :style="{ width: v + '%' }"></div>
            </div>
          </div>
        </div>

        <div class="kicker">Recommended actions</div>
        <div class="actions" v-if="cur.band === 'risk'">
          <div class="action risk">
            <span class="ai-tag">AI</span>
            <div><strong>Escalate to CSM manager</strong> · schedule EBR within 7 days. Score is falling and renewal is inside 90-day window.</div>
          </div>
          <div class="action">
            <span class="ai-tag">AI</span>
            <div><strong>Enable 2 high-value features</strong> not yet in use: multi-market rendering, SSO. Adoption is the biggest gap.</div>
          </div>
        </div>
        <div class="actions" v-else-if="cur.band === 'warn'">
          <div class="action">
            <span class="ai-tag">AI</span>
            <div><strong>Health check call</strong> · Adoption below 80. Consider training bundle add-on.</div>
          </div>
        </div>
        <div class="actions" v-else>
          <div class="action ok">
            <span class="ai-tag">AI</span>
            <div><strong>Expansion candidate</strong> · Route to Upsell engine · projected +${{ Math.round(cur.mrr * 0.3).toLocaleString() }} MRR.</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ch { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-top: 14px; margin-bottom: 8px; font-weight: 700; }
.kicker:first-child { margin-top: 0; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.dimc-i { color: var(--text-dim); font-size: 11px; }

.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi { padding: 16px 18px; border-left: 3px solid var(--border); }
.kpi.ok { border-color: var(--success); }
.kpi.warn { border-color: #fcd34d; }
.kpi.risk { border-color: var(--danger); }
.cn { font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.cn.danger { color: var(--danger); }
.cl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.grid { display: grid; grid-template-columns: 1fr 1.6fr; gap: 16px; align-items: flex-start; }

.list { padding: 14px; display: flex; flex-direction: column; gap: 6px; }
.ac { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); cursor: pointer; }
.ac:hover { border-color: var(--primary); }
.ac.on { border-color: var(--primary); background: rgba(124, 92, 255, .1); }
.ac.risk.on { background: rgba(248, 113, 113, .08); border-color: var(--danger); }
.ac-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.ac-name { font-weight: 700; font-size: 13px; }
.ac-score { font-size: 14px; font-weight: 800; padding: 3px 8px; border-radius: 5px; font-variant-numeric: tabular-nums; }
.ac-score.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.ac-score.warn { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.ac-score.risk { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.ac-meta { display: flex; gap: 6px; font-size: 11px; color: var(--text-dim); align-items: center; flex-wrap: wrap; }
.ac-meta .dot { color: var(--border); }
.trend { font-weight: 600; }
.trend.up { color: var(--success); }
.trend.down { color: var(--danger); }
.trend.flat { color: var(--text-dim); }

.detail { padding: 20px; }
.d-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 8px; flex-wrap: wrap; }
.d-right { display: flex; gap: 20px; }
.d-score { text-align: center; padding: 8px 14px; border-radius: 10px; border: 1px solid; }
.d-score.ok { border-color: rgba(52, 211, 153, .4); background: rgba(52, 211, 153, .06); color: #6ee7b7; }
.d-score.warn { border-color: rgba(251, 191, 36, .4); background: rgba(251, 191, 36, .06); color: #fcd34d; }
.d-score.risk { border-color: rgba(248, 113, 113, .4); background: rgba(248, 113, 113, .06); color: #fca5a5; }
.ds-num { font-size: 26px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.ds-lbl { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; margin-top: 2px; opacity: .8; }
.d-churn { text-align: center; }
.dc-num { font-size: 26px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; color: var(--danger); }
.dc-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.signals { display: flex; flex-direction: column; gap: 10px; }
.sg { padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
.sg-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 12px; }
.sg-k { text-transform: capitalize; }
.sg-v { font-weight: 800; padding: 2px 8px; border-radius: 5px; font-variant-numeric: tabular-nums; }
.sg-v.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.sg-v.warn { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.sg-v.risk { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.sg-bar { height: 5px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.sg-fill { height: 100%; border-radius: 999px; }
.sg-fill.ok { background: var(--success); }
.sg-fill.warn { background: #fcd34d; }
.sg-fill.risk { background: var(--danger); }

.actions { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.action { display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; background: rgba(124, 92, 255, .08); border: 1px solid rgba(124, 92, 255, .25); border-radius: 10px; font-size: 13px; line-height: 1.5; color: var(--text); }
.action.ok { background: rgba(52, 211, 153, .08); border-color: rgba(52, 211, 153, .25); }
.action.risk { background: rgba(248, 113, 113, .08); border-color: rgba(248, 113, 113, .25); }
.ai-tag { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 800; letter-spacing: .05em; flex-shrink: 0; margin-top: 2px; }
.action strong { color: var(--text); }

@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; }
  .kpi-row { grid-template-columns: 1fr 1fr; }
}
</style>
