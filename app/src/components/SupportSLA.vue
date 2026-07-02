<script setup>
import { ref, computed } from 'vue'

const now = Date.now()
function inHours(h) { return new Date(now + h * 3600000).toISOString() }

const tickets = ref([
  { id: 'T-8241', title: 'Render queue stuck · JP region',           account: 'Lumen Studios',   sev: 'SEV1', assignee: 'On-call', due: inHours(-0.5), status: 'active',  sla: 1,  age: '3h 24m', csat: null },
  { id: 'T-8240', title: 'API returning 429 on burst',               account: 'Aurora Media',    sev: 'SEV2', assignee: 'Priya',   due: inHours(4.2),   status: 'active',  sla: 8,  age: '5h 12m', csat: null },
  { id: 'T-8239', title: 'How to enable multi-market rendering',     account: 'Kaito Beauty',    sev: 'SEV3', assignee: 'Marcus',  due: inHours(38),    status: 'active',  sla: 48, age: '10h',    csat: null },
  { id: 'T-8238', title: 'SSO SAML metadata rotation',               account: 'Cobalt Legal',    sev: 'SEV2', assignee: 'Priya',   due: inHours(-2),    status: 'active',  sla: 8,  age: '11h',    csat: null },
  { id: 'T-8237', title: 'Invoice charge dispute · overage',         account: 'Mizu Logistics',  sev: 'SEV3', assignee: 'Sofia',   due: inHours(52),    status: 'active',  sla: 48, age: '4h',     csat: null },
  { id: 'T-8236', title: 'Bulk export missing 6 renders',            account: 'Northwave',       sev: 'SEV2', assignee: 'Marcus',  due: inHours(6),     status: 'resolved',sla: 8,  age: '2d',     csat: 5 },
  { id: 'T-8235', title: 'Onboarding walkthrough scheduling',        account: 'Verda Commerce',  sev: 'SEV3', assignee: 'Sofia',   due: inHours(72),    status: 'resolved',sla: 48, age: '2d',     csat: 5 },
  { id: 'T-8234', title: 'Brand kit sync failed',                    account: 'Lumen Studios',   sev: 'SEV2', assignee: 'Priya',   due: inHours(6),     status: 'resolved',sla: 8,  age: '2d',     csat: 4 }
])

const filter = ref('active')
const filters = ['active', 'resolved', 'all']

const enriched = computed(() => tickets.value.map(t => {
  const hoursLeft = (new Date(t.due) - now) / 3600000
  const pctConsumed = t.status === 'resolved' ? 100 : Math.min(100, (1 - hoursLeft / t.sla) * 100)
  const breach = hoursLeft < 0 && t.status !== 'resolved'
  return { ...t, hoursLeft, pctConsumed, breach }
}))

const filtered = computed(() => filter.value === 'all' ? enriched.value : enriched.value.filter(t => t.status === filter.value))

const summary = computed(() => ({
  active: enriched.value.filter(t => t.status === 'active').length,
  sev1: enriched.value.filter(t => t.sev === 'SEV1' && t.status === 'active').length,
  breach: enriched.value.filter(t => t.breach).length,
  csat: (() => {
    const resolved = enriched.value.filter(t => t.csat)
    return resolved.length ? (resolved.reduce((s, t) => s + t.csat, 0) / resolved.length).toFixed(2) : '—'
  })()
}))

const agents = [
  { name: 'Priya',  active: 3, resolved7d: 18, ftr: '78%' },
  { name: 'Marcus', active: 2, resolved7d: 14, ftr: '82%' },
  { name: 'Sofia',  active: 2, resolved7d: 12, ftr: '76%' },
  { name: 'On-call',active: 1, resolved7d: 4,  ftr: '92%' }
]
</script>

<template>
  <div class="ss">
    <div class="card head">
      <div>
        <div class="kicker">Support · SLA queue</div>
        <h3>{{ summary.active }} active tickets · {{ summary.sev1 }} SEV1 · {{ summary.breach }} breach{{ summary.breach !== 1 ? 'es' : '' }}</h3>
        <p class="meta">SLA clocks pause on customer-blocked state. Breaches auto-escalate + notify account CSM.</p>
      </div>
    </div>

    <div class="kpi-row">
      <div class="card kpi ok">
        <div class="cn">{{ summary.active - summary.sev1 - summary.breach }}</div>
        <div class="cl">On track</div>
      </div>
      <div class="card kpi warn">
        <div class="cn">{{ summary.sev1 }}</div>
        <div class="cl">SEV1 active</div>
      </div>
      <div class="card kpi risk">
        <div class="cn">{{ summary.breach }}</div>
        <div class="cl">SLA breach</div>
      </div>
      <div class="card kpi">
        <div class="cn">{{ summary.csat }}</div>
        <div class="cl">CSAT rolling</div>
      </div>
    </div>

    <div class="card">
      <div class="th-row">
        <h3>Tickets</h3>
        <div class="filt">
          <button v-for="f in filters" :key="f" :class="{ on: filter === f }" @click="filter = f" type="button">{{ f }}</button>
        </div>
      </div>
      <table class="t">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Account</th>
            <th>Sev</th>
            <th>Assignee</th>
            <th>Age</th>
            <th>SLA</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="tk in filtered" :key="tk.id" :class="{ breach: tk.breach }">
            <td>
              <div class="tk-id">{{ tk.id }}</div>
              <div class="tk-title">{{ tk.title }}</div>
            </td>
            <td class="dimc">{{ tk.account }}</td>
            <td><span class="sev" :class="tk.sev.toLowerCase()">{{ tk.sev }}</span></td>
            <td class="dimc">{{ tk.assignee }}</td>
            <td class="dimc">{{ tk.age }}</td>
            <td>
              <div class="sla-row">
                <div class="sla-bar">
                  <div class="sla-fill" :class="tk.breach ? 'breach' : tk.pctConsumed >= 80 ? 'warn' : 'ok'" :style="{ width: Math.min(100, tk.pctConsumed) + '%' }"></div>
                </div>
                <span class="sla-num" :class="tk.breach ? 'breach' : ''">
                  {{ tk.status === 'resolved' ? 'closed' : tk.breach ? 'BREACH · +' + Math.round(-tk.hoursLeft * 60) + 'm' : Math.round(tk.hoursLeft * 60) + 'm left' }}
                </span>
              </div>
            </td>
            <td>
              <span class="st" :class="tk.status">{{ tk.status }}</span>
              <span v-if="tk.csat" class="csat">⭐ {{ tk.csat }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>Agent workload · last 7 days</h3>
      <div class="agents">
        <div v-for="a in agents" :key="a.name" class="agent">
          <div class="a-av">{{ a.name[0] }}</div>
          <div class="a-body">
            <div class="a-name">{{ a.name }}</div>
            <div class="a-meta">{{ a.resolved7d }} resolved · {{ a.ftr }} first-touch resolution</div>
          </div>
          <div class="a-active">
            <div class="aa-num">{{ a.active }}</div>
            <div class="aa-lbl">active</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ss { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi { padding: 16px 18px; border-left: 3px solid var(--border); }
.kpi.ok { border-color: var(--success); }
.kpi.warn { border-color: #fcd34d; }
.kpi.risk { border-color: var(--danger); }
.cn { font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.cl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.th-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.filt { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; }
.filt button { padding: 5px 14px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 12px; text-transform: capitalize; }
.filt button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.t { width: 100%; border-collapse: collapse; font-size: 12px; }
.t th { text-align: left; padding: 10px 8px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.t td { padding: 12px 8px; border-bottom: 1px dashed var(--border); vertical-align: middle; }
.t td.dimc { color: var(--text-dim); }
.t tr.breach td { background: rgba(248, 113, 113, .04); }
.tk-id { font-family: ui-monospace, monospace; color: var(--primary-2); font-weight: 700; font-size: 10px; margin-bottom: 2px; }
.tk-title { font-size: 13px; }

.sev { font-size: 10px; padding: 3px 8px; border-radius: 5px; font-weight: 800; letter-spacing: .05em; }
.sev.sev1 { background: rgba(248, 113, 113, .18); color: #fca5a5; }
.sev.sev2 { background: rgba(251, 191, 36, .18); color: #fcd34d; }
.sev.sev3 { background: rgba(96, 165, 250, .15); color: #93c5fd; }

.sla-row { display: flex; align-items: center; gap: 8px; }
.sla-bar { flex: 1; height: 5px; background: var(--surface-2); border-radius: 999px; overflow: hidden; min-width: 100px; }
.sla-fill { height: 100%; border-radius: 999px; }
.sla-fill.ok { background: var(--success); }
.sla-fill.warn { background: #fcd34d; }
.sla-fill.breach { background: var(--danger); }
.sla-num { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; white-space: nowrap; }
.sla-num.breach { color: var(--danger); font-weight: 800; }

.st { font-size: 10px; padding: 3px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-right: 6px; }
.st.active { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.st.resolved { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.csat { font-size: 11px; color: #fcd34d; }

.agents { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px; }
.agent { display: grid; grid-template-columns: 40px 1fr auto; gap: 12px; align-items: center; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.a-av { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; display: grid; place-items: center; font-weight: 800; }
.a-name { font-weight: 700; font-size: 13px; }
.a-meta { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
.a-active { text-align: right; }
.aa-num { font-size: 20px; font-weight: 800; font-variant-numeric: tabular-nums; color: var(--primary-2); }
.aa-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }

@media (max-width: 1024px) {
  .kpi-row { grid-template-columns: 1fr 1fr; }
  .agents { grid-template-columns: 1fr 1fr; }
  .t th:nth-child(2), .t td:nth-child(2),
  .t th:nth-child(4), .t td:nth-child(4) { display: none; }
}
</style>
