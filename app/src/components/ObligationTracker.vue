<script setup>
import { ref, computed } from 'vue'

const contracts = ref([
  {
    id: 'C-204', name: 'Lumen Studios · JP Distribution', value: 840000, signed: 'Dec 02',
    obligations: [
      { id: 'O-1', kind: 'SLA',         text: 'Render delivery within 72h of asset upload',         owner: 'AdForge Ops',    due: 'Continuous', status: 'on-track', risk: 'low',  next: 'Dec 12' },
      { id: 'O-2', kind: 'Deliverable', text: 'Localized creative for 12 SKUs · JP/KR markets',     owner: 'Creative',       due: 'Dec 15',     status: 'at-risk',  risk: 'high', next: 'Dec 15' },
      { id: 'O-3', kind: 'Report',      text: 'Monthly performance report by 5th business day',     owner: 'Analytics',      due: 'Jan 07',     status: 'on-track', risk: 'low',  next: 'Jan 07' },
      { id: 'O-4', kind: 'Payment',     text: 'Quarterly rebate calc + payment within 30 days EOQ', owner: 'Finance',        due: 'Jan 30',     status: 'on-track', risk: 'low',  next: 'Jan 30' },
      { id: 'O-5', kind: 'Compliance',  text: 'C2PA signatures embedded on every deliverable',       owner: 'AI Safety',      due: 'Continuous', status: 'on-track', risk: 'low',  next: 'continuous' }
    ]
  },
  {
    id: 'C-198', name: 'Northwave Partners · LATAM',     value: 1200000, signed: 'Nov 24',
    obligations: [
      { id: 'O-6', kind: 'Deliverable', text: 'API access + sandbox provisioned within 5 days',     owner: 'Engineering',    due: 'Nov 29',     status: 'done',      risk: 'low',  next: '—' },
      { id: 'O-7', kind: 'SLA',         text: '99.9% uptime · BR + MX regions',                     owner: 'SRE',            due: 'Continuous', status: 'on-track', risk: 'med',  next: 'Dec 10' },
      { id: 'O-8', kind: 'Training',    text: 'Quarterly partner training session · PT/ES',          owner: 'CS',             due: 'Dec 18',     status: 'on-track', risk: 'low',  next: 'Dec 18' }
    ]
  },
  {
    id: 'C-191', name: 'Cobalt Legal · Counsel of record', value: 220000, signed: 'Oct 18',
    obligations: [
      { id: 'O-9',  kind: 'SLA',        text: 'Initial response to legal asks within 24h',           owner: 'Cobalt Legal',   due: 'Continuous', status: 'breach',   risk: 'high', next: 'overdue 6h' },
      { id: 'O-10', kind: 'Deliverable',text: 'Quarterly compliance memo by 15th of month',          owner: 'Cobalt Legal',   due: 'Dec 15',     status: 'on-track', risk: 'low',  next: 'Dec 15' }
    ]
  }
])

const filter = ref('all')
const filters = ['all', 'on-track', 'at-risk', 'breach', 'done']

const flat = computed(() => contracts.value.flatMap(c => c.obligations.map(o => ({ ...o, contract: c.name, contractId: c.id }))))
const filtered = computed(() => filter.value === 'all' ? flat.value : flat.value.filter(o => o.status === filter.value))

const summary = computed(() => ({
  total: flat.value.length,
  ontrack: flat.value.filter(o => o.status === 'on-track').length,
  atrisk: flat.value.filter(o => o.status === 'at-risk').length,
  breach: flat.value.filter(o => o.status === 'breach').length,
  done: flat.value.filter(o => o.status === 'done').length
}))
</script>

<template>
  <div class="ob">
    <div class="card head">
      <div>
        <div class="kicker">Post-signing obligations</div>
        <h3>{{ summary.total }} obligations across {{ contracts.length }} contracts</h3>
        <p class="meta">AI monitors deadlines, SLAs and deliverables. Breaches escalate to the contract owner + Slack.</p>
      </div>
      <div class="sumrow">
        <div class="s"><div class="sn ok-color">{{ summary.ontrack }}</div><div class="sl">on track</div></div>
        <div class="s"><div class="sn warn-color">{{ summary.atrisk }}</div><div class="sl">at risk</div></div>
        <div class="s"><div class="sn risk-color">{{ summary.breach }}</div><div class="sl">breach</div></div>
        <div class="s"><div class="sn dimc">{{ summary.done }}</div><div class="sl">done</div></div>
      </div>
    </div>

    <div class="card">
      <div class="th-row">
        <h3>Obligations</h3>
        <div class="filt">
          <button v-for="f in filters" :key="f" :class="{ on: filter === f }" @click="filter = f" type="button">{{ f }}</button>
        </div>
      </div>
      <table class="t">
        <thead>
          <tr>
            <th>Obligation</th>
            <th>Kind</th>
            <th>Contract</th>
            <th>Owner</th>
            <th>Next deadline</th>
            <th>Status</th>
            <th>AI risk</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in filtered" :key="o.id" :class="o.status">
            <td>
              <div class="o-id">{{ o.id }}</div>
              <div class="o-txt">{{ o.text }}</div>
            </td>
            <td><span class="kind" :class="o.kind.toLowerCase()">{{ o.kind }}</span></td>
            <td class="dimc">{{ o.contract }}</td>
            <td class="dimc">{{ o.owner }}</td>
            <td><span :class="{ overdue: o.next.includes('overdue') }">{{ o.next }}</span></td>
            <td><span class="st" :class="o.status">{{ o.status === 'on-track' ? '✓ on track' : o.status === 'at-risk' ? '! at risk' : o.status === 'breach' ? '✗ breach' : '○ done' }}</span></td>
            <td><span class="rsk" :class="o.risk">{{ o.risk }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.ob { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.sumrow { display: flex; gap: 18px; }
.s { text-align: center; }
.sn { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.sl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }
.ok-color { color: var(--success); }
.warn-color { color: #fcd34d; }
.risk-color { color: var(--danger); }
.dimc { color: var(--text-dim); }

.th-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.filt { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; }
.filt button { padding: 5px 12px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 11px; text-transform: capitalize; }
.filt button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.t { width: 100%; border-collapse: collapse; font-size: 12px; }
.t th { text-align: left; padding: 10px 8px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.t td { padding: 12px 8px; border-bottom: 1px dashed var(--border); vertical-align: top; }
.t tr.breach td { background: rgba(248, 113, 113, .04); }
.t tr.at-risk td { background: rgba(251, 191, 36, .04); }

.o-id { font-family: ui-monospace, monospace; color: var(--primary-2); font-weight: 700; font-size: 10px; margin-bottom: 4px; }
.o-txt { font-size: 13px; line-height: 1.4; }

.kind { font-size: 10px; padding: 2px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.kind.sla { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.kind.deliverable { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.kind.report { background: rgba(96, 165, 250, .15); color: #93c5fd; }
.kind.payment { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.kind.compliance { background: rgba(255, 122, 217, .15); color: #f5d0fe; }
.kind.training { background: rgba(251, 191, 36, .15); color: #fcd34d; }

.st { font-size: 10px; padding: 3px 8px; border-radius: 5px; font-weight: 700; }
.st.on-track { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.st.at-risk { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.st.breach { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.st.done { background: var(--surface-2); color: var(--text-dim); }

.rsk { font-size: 10px; padding: 2px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.rsk.low { background: rgba(52, 211, 153, .12); color: #6ee7b7; }
.rsk.med { background: rgba(251, 191, 36, .12); color: #fcd34d; }
.rsk.high { background: rgba(248, 113, 113, .12); color: #fca5a5; }

.overdue { color: var(--danger); font-weight: 700; }

@media (max-width: 900px) {
  .t th:nth-child(3), .t td:nth-child(3),
  .t th:nth-child(4), .t td:nth-child(4) { display: none; }
}
</style>
