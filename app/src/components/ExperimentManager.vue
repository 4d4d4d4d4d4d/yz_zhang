<script setup>
import { ref, computed } from 'vue'

const experiments = ref([
  {
    id: 'EXP-204', name: 'Two-tower v17 ranking',
    primary: 'NDCG@10', status: 'ramping',
    mutex: 'ranking',
    arms: [
      { name: 'Control · v16', share: 50, users: 624000, metric: 0.461, lift: 0, pval: '—' },
      { name: 'Treatment · v17', share: 50, users: 622000, metric: 0.482, lift: 4.6, pval: '0.003' }
    ],
    days: 9, started: 'Nov 24',
    guardrails: [
      { name: 'p95 latency', val: '+2ms', status: 'ok' },
      { name: 'Error rate',  val: '+0.01%', status: 'ok' }
    ]
  },
  {
    id: 'EXP-205', name: 'Bandit promotion · creative arms',
    primary: 'CVR', status: 'shipped',
    mutex: 'creative',
    arms: [
      { name: 'Control · uniform', share: 20, users: 184000, metric: 2.4, lift: 0, pval: '—' },
      { name: 'Treatment · bandit', share: 80, users: 736000, metric: 3.1, lift: 29.2, pval: '<0.001' }
    ],
    days: 21, started: 'Nov 12',
    guardrails: [
      { name: 'Brand-safety flags', val: '+0', status: 'ok' },
      { name: 'CPA',                val: '−$3', status: 'ok' }
    ]
  },
  {
    id: 'EXP-206', name: 'Audience builder · LTV scoring v2',
    primary: 'ROAS', status: 'ramping',
    mutex: 'audience',
    arms: [
      { name: 'Control · LTV v1', share: 50, users: 412000, metric: 3.4, lift: 0, pval: '—' },
      { name: 'Treatment · LTV v2', share: 50, users: 408000, metric: 3.6, lift: 5.9, pval: '0.084' }
    ],
    days: 6, started: 'Nov 28',
    guardrails: [
      { name: 'Reach',          val: '−4%',  status: 'warn' },
      { name: 'Overlap',        val: '+1pt', status: 'ok' }
    ]
  },
  {
    id: 'EXP-207', name: 'Cold-start · 7-day diary hook',
    primary: 'D1 retention', status: 'holdout',
    mutex: 'creative',
    arms: [
      { name: 'Holdout',       share: 5,  users: 46000,  metric: 0.42, lift: 0, pval: '—' },
      { name: 'Always-on hook', share: 95, users: 874000, metric: 0.48, lift: 14.3, pval: '<0.001' }
    ],
    days: 41, started: 'Oct 24',
    guardrails: [
      { name: 'Frequency',  val: '+12%', status: 'warn' },
      { name: 'Unsubscribes',val: '+0.0%',status: 'ok' }
    ]
  }
])

const selected = ref('EXP-204')
const cur = computed(() => experiments.value.find(e => e.id === selected.value))

const mutexGroups = computed(() => {
  const g = {}
  for (const e of experiments.value) (g[e.mutex] ??= []).push(e.id)
  return g
})

function statusLabel(s) {
  return { ramping: 'Ramping', shipped: 'Shipped', holdout: 'Holdout', paused: 'Paused' }[s]
}
</script>

<template>
  <div class="ex">
    <div class="card head">
      <div>
        <div class="kicker">Experiments</div>
        <h3>{{ experiments.length }} live · {{ experiments.filter(e => e.status === 'ramping').length }} ramping</h3>
        <p class="meta">Mutual exclusion groups guarantee no user is in two conflicting experiments at once.</p>
      </div>
      <div class="mx-groups">
        <div v-for="(ids, k) in mutexGroups" :key="k" class="mx">
          <span class="mx-k">{{ k }}</span>
          <span class="mx-c">{{ ids.length }} exp</span>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card list">
        <div v-for="e in experiments" :key="e.id"
          class="li" :class="{ on: selected === e.id, [e.status]: true }"
          @click="selected = e.id">
          <div class="li-top">
            <span class="li-id">{{ e.id }}</span>
            <span class="li-st" :class="e.status">{{ statusLabel(e.status) }}</span>
          </div>
          <div class="li-name">{{ e.name }}</div>
          <div class="li-meta">
            <span>{{ e.primary }}</span>
            <span class="dot">·</span>
            <span>mutex <code>{{ e.mutex }}</code></span>
            <span class="dot">·</span>
            <span>day {{ e.days }}</span>
          </div>
          <div class="li-lift">
            <span :class="e.arms[1].lift > 0 ? 'pos' : 'neg'">
              {{ e.arms[1].lift > 0 ? '+' : '' }}{{ e.arms[1].lift }}%
            </span>
            <span class="li-pval">p = {{ e.arms[1].pval }}</span>
          </div>
        </div>
      </div>

      <div class="card detail">
        <div class="d-head">
          <div>
            <div class="kicker">{{ cur.id }} · started {{ cur.started }} · day {{ cur.days }}</div>
            <h3>{{ cur.name }}</h3>
          </div>
          <div class="d-actions">
            <button class="btn btn-ghost sm" type="button">Pause</button>
            <button class="btn btn-primary sm" :disabled="cur.status === 'shipped'" type="button">Ship treatment</button>
          </div>
        </div>

        <div class="arms">
          <div v-for="(a, i) in cur.arms" :key="a.name" class="arm" :class="{ winner: i === 1 && a.lift > 0 && a.pval !== '—' && parseFloat(a.pval) < 0.05 }">
            <div class="a-head">
              <span class="a-name">{{ a.name }}</span>
              <span class="a-share">{{ a.share }}% · {{ a.users.toLocaleString() }} users</span>
            </div>
            <div class="a-bar">
              <div class="a-fill" :style="{ width: a.share + '%', background: i === 0 ? 'var(--text-dim)' : 'linear-gradient(90deg, var(--primary), var(--primary-2))' }"></div>
            </div>
            <div class="a-foot">
              <div><div class="an">{{ a.metric }}</div><div class="al">{{ cur.primary }}</div></div>
              <div v-if="i > 0">
                <div class="an" :class="a.lift > 0 ? 'pos' : 'neg'">{{ a.lift > 0 ? '+' : '' }}{{ a.lift }}%</div>
                <div class="al">vs control</div>
              </div>
              <div v-if="i > 0">
                <div class="an" :class="a.pval !== '—' && parseFloat(a.pval) < 0.05 ? 'pos' : ''">{{ a.pval }}</div>
                <div class="al">p-value</div>
              </div>
            </div>
          </div>
        </div>

        <div class="kicker">Guardrails</div>
        <div class="guards">
          <div v-for="g in cur.guardrails" :key="g.name" class="g" :class="g.status">
            <span class="g-status">{{ g.status === 'ok' ? '✓' : g.status === 'warn' ? '!' : '✗' }}</span>
            <span class="g-name">{{ g.name }}</span>
            <span class="g-val">{{ g.val }}</span>
          </div>
        </div>

        <div class="kicker">Mutex group · {{ cur.mutex }}</div>
        <div class="mx-info">
          Other experiments in this group are de-prioritized when a user is enrolled here.
          <div class="mx-list">
            <span v-for="id in mutexGroups[cur.mutex].filter(x => x !== cur.id)" :key="id" class="tag">{{ id }}</span>
            <span v-if="mutexGroups[cur.mutex].length === 1" class="dimc-i">No other experiments in this group.</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ex { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-top: 12px; }
.kicker:first-child { margin-top: 0; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.mx-groups { display: flex; gap: 8px; flex-wrap: wrap; }
.mx { padding: 6px 12px; border-radius: 8px; background: var(--surface); border: 1px solid var(--border); font-size: 12px; display: flex; align-items: center; gap: 8px; }
.mx-k { font-weight: 700; color: var(--primary-2); }
.mx-c { color: var(--text-dim); font-size: 11px; }

.grid { display: grid; grid-template-columns: 1fr 1.4fr; gap: 16px; align-items: flex-start; }

.list { padding: 14px; display: flex; flex-direction: column; gap: 6px; }
.li { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); cursor: pointer; }
.li:hover { border-color: var(--primary); }
.li.on { border-color: var(--primary); background: rgba(124, 92, 255, .1); }
.li-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.li-id { font-family: ui-monospace, monospace; font-size: 11px; color: var(--primary-2); font-weight: 700; }
.li-st { font-size: 9px; padding: 2px 7px; border-radius: 4px; text-transform: uppercase; letter-spacing: .05em; font-weight: 700; }
.li-st.ramping { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.li-st.shipped { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.li-st.holdout { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.li-st.paused { background: var(--surface-2); color: var(--text-dim); }
.li-name { font-weight: 600; font-size: 13px; margin-bottom: 6px; }
.li-meta { display: flex; gap: 6px; align-items: center; font-size: 11px; color: var(--text-dim); flex-wrap: wrap; }
.li-meta code { background: var(--surface-2); padding: 1px 5px; border-radius: 3px; font-family: ui-monospace, monospace; font-size: 10px; }
.li-meta .dot { color: var(--border); }
.li-lift { display: flex; gap: 10px; margin-top: 8px; font-size: 12px; font-weight: 700; align-items: center; }
.li-lift .pos { color: var(--success); }
.li-lift .neg { color: var(--danger); }
.li-pval { font-size: 11px; color: var(--text-dim); font-weight: 500; font-variant-numeric: tabular-nums; }

.detail { padding: 20px; }
.d-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
.d-actions { display: flex; gap: 8px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }
.btn.sm:disabled { opacity: .4; cursor: not-allowed; }

.arms { display: flex; flex-direction: column; gap: 12px; margin-bottom: 4px; }
.arm { padding: 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.arm.winner { border-color: var(--success); background: rgba(52, 211, 153, .06); }
.a-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.a-name { font-weight: 600; font-size: 13px; }
.a-share { color: var(--text-dim); font-size: 12px; font-variant-numeric: tabular-nums; }
.a-bar { height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-bottom: 10px; }
.a-fill { height: 100%; }
.a-foot { display: flex; gap: 24px; }
.an { font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.an.pos { color: var(--success); }
.an.neg { color: var(--danger); }
.al { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.guards { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.g { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 8px; background: var(--surface); border: 1px solid var(--border); font-size: 12px; }
.g.ok { background: rgba(52, 211, 153, .08); border-color: rgba(52, 211, 153, .3); }
.g.warn { background: rgba(251, 191, 36, .08); border-color: rgba(251, 191, 36, .3); }
.g.risk { background: rgba(248, 113, 113, .08); border-color: rgba(248, 113, 113, .3); }
.g-status { font-weight: 800; }
.g.ok .g-status { color: var(--success); }
.g.warn .g-status { color: #fcd34d; }
.g.risk .g-status { color: var(--danger); }
.g-val { color: var(--text-dim); font-variant-numeric: tabular-nums; }

.mx-info { font-size: 13px; color: var(--text-dim); margin-top: 8px; }
.mx-list { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.tag { padding: 3px 10px; border-radius: 6px; background: var(--surface-2); border: 1px solid var(--border); font-size: 11px; font-family: ui-monospace, monospace; color: var(--primary-2); }
.dimc-i { color: var(--text-dim); font-size: 12px; font-style: italic; }

@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; }
}
</style>
