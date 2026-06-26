<script setup>
import { ref, computed } from 'vue'

const audit = {
  id: 'AUD-2025-Q4-SOC2',
  type: 'SOC 2 Type II',
  auditor: 'Brightline Audit Group',
  lead: 'Priya R. (Lead auditor)',
  window: 'Sep 01 → Nov 30, 2025',
  status: 'In progress',
  progress: 64,
  scope: 'Trust services criteria: Security · Availability · Confidentiality'
}

const requests = ref([
  { id: 'PBC-01', title: 'Org chart & list of in-scope systems',           area: 'Governance', evidence: 4, comments: 2, status: 'satisfied',  due: 'Nov 04', responder: 'CISO' },
  { id: 'PBC-02', title: 'Access provisioning & deprovisioning logs (Q3)', area: 'Logical access', evidence: 12, comments: 5, status: 'satisfied',  due: 'Nov 12', responder: 'IT Ops' },
  { id: 'PBC-03', title: 'Change management tickets sample (n=25)',        area: 'Change mgmt', evidence: 25, comments: 3, status: 'satisfied',  due: 'Nov 18', responder: 'Eng' },
  { id: 'PBC-04', title: 'Vulnerability scans + remediation evidence',     area: 'Security', evidence: 8, comments: 1, status: 'in-review', due: 'Nov 26', responder: 'SecOps' },
  { id: 'PBC-05', title: 'Incident response postmortems (last 12mo)',       area: 'IR', evidence: 6, comments: 4, status: 'in-review', due: 'Nov 28', responder: 'SRE' },
  { id: 'PBC-06', title: 'Backup tests + RTO/RPO validation',              area: 'Availability', evidence: 3, comments: 7, status: 'awaiting', due: 'Dec 04', responder: 'SRE' },
  { id: 'PBC-07', title: 'Subprocessor due-diligence (top 12 vendors)',    area: 'Vendor', evidence: 0, comments: 2, status: 'pending', due: 'Dec 08', responder: 'Procurement' },
  { id: 'PBC-08', title: 'Annual security training completion (≥95%)',     area: 'People', evidence: 2, comments: 0, status: 'pending', due: 'Dec 12', responder: 'HR' }
])

const filter = ref('all')
const filters = ['all', 'pending', 'awaiting', 'in-review', 'satisfied']

const filtered = computed(() => filter.value === 'all' ? requests.value : requests.value.filter(r => r.status === filter.value))

const summary = computed(() => ({
  total: requests.value.length,
  satisfied: requests.value.filter(r => r.status === 'satisfied').length,
  active: requests.value.filter(r => r.status === 'in-review' || r.status === 'awaiting').length,
  pending: requests.value.filter(r => r.status === 'pending').length,
  evidence: requests.value.reduce((s, r) => s + r.evidence, 0)
}))

const access = [
  { who: 'Priya R. · Brightline',  what: 'viewed PBC-04 (Vulnerability scans)',  when: '3m ago',  src: '2 of 8 evidence files' },
  { who: 'Brightline · IP 73.x',   what: 'downloaded PBC-03 evidence bundle (signed URL)', when: '21m ago', src: '14.2 MB · expires in 2h' },
  { who: 'CISO',                    what: 'replied to comment on PBC-04',         when: '1h ago',  src: '—' },
  { who: 'auto-policy',             what: 'rotated read-only token for Brightline', when: '2h ago',  src: 'new TTL 24h' },
  { who: 'Priya R. · Brightline',  what: 'opened PBC-05 (IR postmortems)',       when: '4h ago',  src: 'viewed 4 of 6 evidence files' }
]
</script>

<template>
  <div class="ar">
    <div class="card head">
      <div>
        <div class="kicker">{{ audit.type }} · {{ audit.id }}</div>
        <h3>{{ audit.scope }}</h3>
        <p class="meta">Window {{ audit.window }} · Auditor {{ audit.auditor }} · {{ audit.lead }}</p>
      </div>
      <div class="prog">
        <div class="prog-num grad-text">{{ audit.progress }}%</div>
        <div class="prog-lbl">satisfied</div>
        <div class="prog-bar"><div class="prog-fill" :style="{ width: audit.progress + '%' }"></div></div>
      </div>
    </div>

    <div class="cat-row">
      <div class="card cat ok">
        <div class="cn">{{ summary.satisfied }}<span class="cd">/ {{ summary.total }}</span></div>
        <div class="cl">Satisfied</div>
      </div>
      <div class="card cat warn">
        <div class="cn">{{ summary.active }}</div>
        <div class="cl">In review</div>
      </div>
      <div class="card cat">
        <div class="cn">{{ summary.pending }}</div>
        <div class="cl">Pending response</div>
      </div>
      <div class="card cat info">
        <div class="cn">{{ summary.evidence }}</div>
        <div class="cl">Evidence files</div>
      </div>
    </div>

    <div class="card">
      <div class="th-row">
        <h3>Requests · PBC</h3>
        <div class="filt">
          <button v-for="f in filters" :key="f" :class="{ on: filter === f }" @click="filter = f" type="button">{{ f }}</button>
        </div>
      </div>
      <table class="t">
        <thead>
          <tr>
            <th>Request</th>
            <th>Area</th>
            <th class="num">Evidence</th>
            <th class="num">Comments</th>
            <th>Owner</th>
            <th>Due</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td>
              <div class="r-id">{{ r.id }}</div>
              <div class="r-title">{{ r.title }}</div>
            </td>
            <td class="dimc">{{ r.area }}</td>
            <td class="num">{{ r.evidence }}</td>
            <td class="num">{{ r.comments }}</td>
            <td class="dimc">{{ r.responder }}</td>
            <td class="dimc">{{ r.due }}</td>
            <td><span class="st" :class="r.status">{{ r.status }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>Auditor access log</h3>
      <p class="meta">All auditor activity is logged. Tokens auto-rotate every 24h.</p>
      <ul class="log">
        <li v-for="(e, i) in access" :key="i">
          <span class="who" :class="{ ext: e.who.includes('Brightline'), auto: e.who.startsWith('auto') }">{{ e.who }}</span>
          <span class="what">{{ e.what }}<span class="src"> — {{ e.src }}</span></span>
          <span class="when">{{ e.when }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.ar { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.prog { text-align: right; min-width: 200px; }
.prog-num { font-size: 32px; font-weight: 800; line-height: 1; }
.prog-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }
.prog-bar { width: 200px; height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-top: 10px; margin-left: auto; }
.prog-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }

.cat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.cat { padding: 16px 18px; border-left: 3px solid var(--border); }
.cat.ok { border-color: var(--success); }
.cat.warn { border-color: #fcd34d; }
.cat.info { border-color: var(--primary-2); }
.cn { font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.cd { font-size: 13px; color: var(--text-dim); margin-left: 4px; }
.cl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.th-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.filt { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; }
.filt button { padding: 5px 12px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 11px; text-transform: capitalize; }
.filt button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.t { width: 100%; border-collapse: collapse; font-size: 12px; }
.t th { text-align: left; padding: 10px 8px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.t th.num { text-align: right; }
.t td { padding: 12px 8px; border-bottom: 1px dashed var(--border); }
.t td.num { text-align: right; font-variant-numeric: tabular-nums; }
.t td.dimc { color: var(--text-dim); }
.r-id { font-family: ui-monospace, monospace; color: var(--primary-2); font-weight: 700; font-size: 10px; margin-bottom: 2px; }
.r-title { font-size: 13px; font-weight: 500; }

.st { font-size: 10px; padding: 3px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.st.satisfied { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.st.in-review { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.st.awaiting { background: rgba(96, 165, 250, .15); color: #93c5fd; }
.st.pending { background: var(--surface-2); color: var(--text-dim); }

.log { list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 2px; }
.log li { display: grid; grid-template-columns: 200px 1fr 100px; gap: 14px; padding: 10px 0; border-bottom: 1px dashed var(--border); font-size: 12px; }
.log li:last-child { border-bottom: 0; }
.who { font-weight: 700; }
.who.ext { color: #fcd34d; }
.who.auto { color: var(--primary-2); }
.what { color: var(--text); }
.src { color: var(--text-dim); font-size: 11px; margin-left: 4px; }
.when { color: var(--text-dim); text-align: right; font-size: 11px; }

@media (max-width: 1024px) {
  .cat-row { grid-template-columns: 1fr 1fr; }
  .log li { grid-template-columns: 1fr; gap: 2px; }
  .when { text-align: left; }
}
</style>
