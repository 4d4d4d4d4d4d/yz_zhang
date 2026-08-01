<script setup>
import { ref, computed } from 'vue'
import { createDSR, dsrStatus, hoursRemaining, summarizeDSR } from '../logic/dsr.js'

const frameworks = ['GDPR', 'CCPA', 'APPI', 'LGPD', 'SOC2', 'ISO27001']

const controls = [
  { id: 'AC-01', name: 'Access control · least privilege', owner: 'Engineering', map: { GDPR: 'auto', CCPA: 'auto', APPI: 'auto', LGPD: 'auto', SOC2: 'auto', ISO27001: 'auto' } },
  { id: 'AC-02', name: 'MFA for all admin accounts',       owner: 'Engineering', map: { GDPR: 'auto', CCPA: 'auto', APPI: 'auto', LGPD: 'auto', SOC2: 'auto', ISO27001: 'auto' } },
  { id: 'AU-01', name: 'Audit log retention (1 year)',     owner: 'Engineering', map: { GDPR: 'auto', CCPA: 'auto', APPI: 'auto', LGPD: 'auto', SOC2: 'auto', ISO27001: 'auto' } },
  { id: 'CP-01', name: 'Backup &amp; recovery tested quarterly', owner: 'Engineering', map: { GDPR: 'manual', CCPA: 'na',   APPI: 'manual', LGPD: 'manual', SOC2: 'auto', ISO27001: 'auto' } },
  { id: 'DP-01', name: 'Data Processing Agreement signed',  owner: 'Legal',       map: { GDPR: 'auto', CCPA: 'auto', APPI: 'auto', LGPD: 'auto', SOC2: 'na',   ISO27001: 'na' } },
  { id: 'DP-02', name: 'Cross-border transfer SCCs in place', owner: 'Legal',     map: { GDPR: 'auto', CCPA: 'na',   APPI: 'manual', LGPD: 'pending', SOC2: 'na',   ISO27001: 'na' } },
  { id: 'IR-01', name: 'Incident response runbook reviewed', owner: 'Security',  map: { GDPR: 'auto', CCPA: 'auto', APPI: 'auto', LGPD: 'auto', SOC2: 'auto', ISO27001: 'auto' } },
  { id: 'PII-01', name: 'PII inventory + classification',   owner: 'Privacy',    map: { GDPR: 'auto', CCPA: 'auto', APPI: 'auto', LGPD: 'manual', SOC2: 'manual', ISO27001: 'manual' } },
  { id: 'PII-02', name: 'Right to delete · automated',      owner: 'Privacy',    map: { GDPR: 'auto', CCPA: 'auto', APPI: 'auto', LGPD: 'auto', SOC2: 'na', ISO27001: 'na' } },
  { id: 'AI-01', name: 'AI provenance · C2PA signatures',   owner: 'AI Safety',  map: { GDPR: 'auto', CCPA: 'na',   APPI: 'na',   LGPD: 'na',   SOC2: 'manual', ISO27001: 'manual' } },
  { id: 'VEN-01', name: 'Vendor risk assessed pre-onboard', owner: 'Procurement', map: { GDPR: 'manual', CCPA: 'manual', APPI: 'manual', LGPD: 'manual', SOC2: 'auto', ISO27001: 'auto' } },
  { id: 'TR-01', name: 'Annual security training',          owner: 'HR',         map: { GDPR: 'auto', CCPA: 'auto', APPI: 'pending', LGPD: 'auto', SOC2: 'auto', ISO27001: 'auto' } }
]

const fwFilter = ref('all')

const matrixScore = computed(() => {
  let total = 0, ok = 0
  for (const c of controls) {
    for (const f of frameworks) {
      const v = c.map[f]
      if (v === 'na') continue
      total++; if (v === 'auto') ok++
      else if (v === 'manual') ok += 0.7
    }
  }
  return Math.round((ok / total) * 100)
})

const vendors = [
  { name: 'Cobalt Legal',   kind: 'Legal',       region: 'DE', score: 92, residual: 'low',  last: 'Nov 2025' },
  { name: 'Aurora Media',   kind: 'Media',       region: 'SG', score: 88, residual: 'low',  last: 'Oct 2025' },
  { name: 'Mizu Logistics', kind: 'Logistics',   region: 'JP', score: 76, residual: 'med',  last: 'Sep 2025' },
  { name: 'Helio Network',  kind: 'Influencer',  region: 'BR', score: 62, residual: 'med',  last: 'Jul 2025' },
  { name: 'OpenAI',         kind: 'AI subprocessor', region: 'US', score: 90, residual: 'low', last: 'Dec 2025' },
  { name: 'AWS · ap-northeast-1', kind: 'Cloud', region: 'JP', score: 96, residual: 'low', last: 'Dec 2025' }
]

// Spec 42 — deadlines derive from the regime + when the request arrived,
// relative to `now`, so the queue never goes stale like a hardcoded date does.
const now = Date.now()
const DAY = 86400000
const RAW_DSR = [
  { id: 'DSR-2841', type: 'access',      regime: 'GDPR', region: 'EU', from: 'k.m**l@gmx.de',         receivedDaysAgo: 12 },
  { id: 'DSR-2842', type: 'erasure',     regime: 'GDPR', region: 'EU', from: 'a.s**a@protonmail.com', receivedDaysAgo: 26 },
  { id: 'DSR-2843', type: 'portability', regime: 'CCPA', region: 'US', from: 'm**ria@x.example',      receivedDaysAgo: 9 },
  { id: 'DSR-2844', type: 'access',      regime: 'APPI', region: 'JP', from: 't.t****a@i.example',    receivedDaysAgo: 16 },
  { id: 'DSR-2845', type: 'erasure',     regime: 'LGPD', region: 'BR', from: 'r.s****a@u.example',    receivedDaysAgo: 3 }
]
const dsrs = computed(() => RAW_DSR.map(r => {
  const rec = createDSR({ id: r.id, type: r.type, regime: r.regime, subject: r.from, receivedAt: now - r.receivedDaysAgo * DAY })
  const totalHours = (rec.dueAt - rec.receivedAt) / 3600000
  const left = hoursRemaining(rec, now)
  return { ...rec, region: r.region, from: r.from, status: dsrStatus(rec, now), hoursLeft: left, pct: Math.min(100, Math.max(0, (1 - left / totalHours) * 100)) }
}))
const dsrSummary = computed(() => summarizeDSR(dsrs.value, now))

const incident = {
  id: 'INC-104',
  severity: 'SEV-2',
  title: 'Elevated 4xx rate from JP edge (Dec 02 14:22)',
  steps: [
    { i: 'Detect',    text: 'Auto-paged via Datadog · 14:22',           status: 'done',    when: '14:22' },
    { i: 'Triage',    text: 'On-call confirmed: JP edge routing issue', status: 'done',    when: '14:28' },
    { i: 'Contain',   text: 'Failover JP traffic to US-west',           status: 'doing',   when: '14:34' },
    { i: 'Notify',    text: 'Email status to affected partners',        status: 'pending', when: '—' },
    { i: 'Postmortem', text: 'Schedule blameless review · within 5d',   status: 'pending', when: '—' }
  ]
}

const sevScore = (r) => ({ low: 'ok', med: 'warn', high: 'risk' }[r])
</script>

<template>
  <div class="reg">
    <div class="card">
      <div class="h-row">
        <div>
          <h3>Controls × Frameworks</h3>
          <p class="meta">{{ controls.length }} controls across {{ frameworks.length }} frameworks · coverage {{ matrixScore }}%</p>
        </div>
        <div class="fw-pick">
          <button :class="{ on: fwFilter === 'all' }" @click="fwFilter = 'all'" type="button">All</button>
          <button v-for="f in frameworks" :key="f" :class="{ on: fwFilter === f }" @click="fwFilter = f" type="button">{{ f }}</button>
        </div>
      </div>

      <div class="matrix-wrap">
        <table class="matrix">
          <thead>
            <tr>
              <th class="cl">Control</th>
              <th class="ow">Owner</th>
              <th v-for="f in frameworks" :key="f"
                :class="{ dim: fwFilter !== 'all' && fwFilter !== f }">{{ f }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in controls" :key="c.id">
              <td class="cl">
                <div class="cid">{{ c.id }}</div>
                <div class="cnm" v-html="c.name"></div>
              </td>
              <td class="ow">{{ c.owner }}</td>
              <td v-for="f in frameworks" :key="f"
                :class="{ dim: fwFilter !== 'all' && fwFilter !== f }">
                <span class="pill" :class="c.map[f]">
                  {{ c.map[f] === 'auto' ? '✓ auto' : c.map[f] === 'manual' ? '✓ manual' : c.map[f] === 'pending' ? '◷ pending' : '—' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="leg">
        <span><span class="pill auto sm">✓ auto</span> evidence collected by integration</span>
        <span><span class="pill manual sm">✓ manual</span> uploaded by control owner</span>
        <span><span class="pill pending sm">◷ pending</span> due within SLA</span>
        <span><span class="pill na sm">—</span> not applicable</span>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <div class="h-row">
          <h3>Vendor risk register</h3>
          <span class="meta">{{ vendors.length }} active subprocessors</span>
        </div>
        <table class="vt">
          <thead>
            <tr><th>Vendor</th><th>Kind</th><th>Region</th><th class="num">Score</th><th>Residual</th><th>Last review</th></tr>
          </thead>
          <tbody>
            <tr v-for="v in vendors" :key="v.name">
              <td><strong>{{ v.name }}</strong></td>
              <td class="dimc">{{ v.kind }}</td>
              <td class="dimc">{{ v.region }}</td>
              <td class="num"><span class="sb" :class="v.score >= 85 ? 'ok' : v.score >= 70 ? 'warn' : 'risk'">{{ v.score }}</span></td>
              <td><span class="pill" :class="sevScore(v.residual)">{{ v.residual }}</span></td>
              <td class="dimc">{{ v.last }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <div class="h-row">
          <h3>DSR queue</h3>
          <span class="meta">{{ dsrSummary.total }} open · {{ dsrSummary.overdue }} overdue · statutory SLA per regime</span>
        </div>
        <div class="dsr">
          <div v-for="d in dsrs" :key="d.id" class="dsr-row" :class="d.status">
            <div class="d-id">{{ d.id }}</div>
            <div class="d-kind" :class="d.type">{{ d.type }}</div>
            <div class="d-from">{{ d.from }}<span class="d-reg">{{ d.region }} · {{ d.regime }}</span></div>
            <div class="d-sla">
              <div class="d-sla-bar"><div class="d-sla-fill" :class="d.status" :style="{ width: d.pct + '%' }"></div></div>
              <span class="d-sla-num" :class="d.status">{{ d.status === 'overdue' ? 'overdue' : d.hoursLeft + 'h left' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="h-row">
        <div>
          <h3>{{ incident.id }} · {{ incident.title }}</h3>
          <p class="meta">Live runbook · severity <strong class="sev2">{{ incident.severity }}</strong></p>
        </div>
        <button class="btn btn-ghost sm" type="button">Open postmortem</button>
      </div>
      <div class="runbook">
        <div v-for="(s, i) in incident.steps" :key="i" class="rstep" :class="s.status">
          <div class="ri">{{ i + 1 }}</div>
          <div class="rb">
            <div class="rh">
              <span class="rname">{{ s.i }}</span>
              <span class="rwhen">{{ s.when }}</span>
            </div>
            <div class="rt">{{ s.text }}</div>
          </div>
          <span class="rs" :class="s.status">{{ s.status === 'done' ? '✓' : s.status === 'doing' ? '●' : '○' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reg { display: flex; flex-direction: column; gap: 16px; }
.h-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 14px; flex-wrap: wrap; }
.meta { color: var(--text-dim); font-size: 12px; margin: 4px 0 0; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.fw-pick { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; flex-wrap: wrap; }
.fw-pick button { padding: 5px 10px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 11px; font-weight: 600; }
.fw-pick button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.matrix-wrap { overflow-x: auto; }
.matrix { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 800px; }
.matrix th { text-align: center; padding: 10px 8px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; font-size: 10px; border-bottom: 1px solid var(--border); font-weight: 700; }
.matrix th.cl, .matrix th.ow { text-align: left; }
.matrix td { padding: 10px 8px; border-bottom: 1px dashed var(--border); text-align: center; }
.matrix td.cl { text-align: left; min-width: 240px; }
.matrix td.ow { text-align: left; color: var(--text-dim); font-size: 11px; }
.matrix tr:hover td { background: rgba(124, 92, 255, .04); }
.cid { font-family: ui-monospace, monospace; color: var(--primary-2); font-size: 10px; margin-bottom: 2px; }
.cnm { font-size: 13px; font-weight: 500; }
.matrix .dim { opacity: .25; }

.pill { display: inline-block; font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 700; letter-spacing: .04em; }
.pill.auto { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.pill.manual { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.pill.pending { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.pill.na { background: var(--surface-2); color: var(--text-dim); }
.pill.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.pill.warn { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.pill.risk { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.pill.sm { font-size: 10px; padding: 2px 6px; }

.leg { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-dim); align-items: center; }

.row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }

.vt { width: 100%; border-collapse: collapse; font-size: 13px; }
.vt th { text-align: left; padding: 8px 10px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.vt th.num { text-align: right; }
.vt td { padding: 10px; border-bottom: 1px dashed var(--border); }
.vt td.num { text-align: right; }
.vt .dimc { color: var(--text-dim); font-size: 12px; }
.sb { font-weight: 800; font-variant-numeric: tabular-nums; padding: 2px 8px; border-radius: 6px; }
.sb.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.sb.warn { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.sb.risk { background: rgba(248, 113, 113, .15); color: #fca5a5; }

.dsr { display: flex; flex-direction: column; gap: 8px; }
.d-sla-fill.overdue { background: var(--danger) !important; }
.d-sla-fill.due_soon { background: #fbbf24 !important; }
.d-sla-num.overdue { color: var(--danger); font-weight: 700; }
.d-sla-num.due_soon { color: #fbbf24; }
.dsr-row.overdue { border-color: rgba(248, 113, 113, .4); }
.dsr-row { display: grid; grid-template-columns: 90px 70px 1fr 1.2fr; gap: 10px; align-items: center; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); font-size: 12px; }
.d-id { font-family: ui-monospace, monospace; font-size: 11px; color: var(--primary-2); }
.d-kind { font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 700; text-transform: uppercase; text-align: center; }
.d-kind.access { background: rgba(96, 165, 250, .15); color: #93c5fd; }
.d-kind.delete { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.d-kind.export { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.d-from { font-size: 12px; display: flex; gap: 8px; align-items: center; }
.d-reg { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: var(--surface-2); color: var(--text-dim); }
.d-sla { display: flex; gap: 8px; align-items: center; }
.d-sla-bar { flex: 1; height: 4px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.d-sla-fill { height: 100%; background: linear-gradient(90deg, var(--success), #fcd34d 60%, var(--danger)); }
.d-sla-num { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; white-space: nowrap; }

.sev2 { color: #fcd34d; padding: 1px 6px; border-radius: 4px; background: rgba(251, 191, 36, .15); font-size: 12px; }
.runbook { display: flex; flex-direction: column; gap: 10px; margin-top: 8px; }
.rstep { display: grid; grid-template-columns: 28px 1fr auto; gap: 12px; align-items: center; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.rstep.done { border-color: rgba(52, 211, 153, .3); background: rgba(52, 211, 153, .04); }
.rstep.doing { border-color: rgba(251, 191, 36, .35); background: rgba(251, 191, 36, .05); }
.ri { width: 28px; height: 28px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; font-weight: 700; font-size: 12px; color: var(--text-dim); }
.rstep.done .ri { background: var(--success); color: #0a0a0f; }
.rstep.doing .ri { background: #fcd34d; color: #0a0a0f; }
.rh { display: flex; gap: 12px; align-items: baseline; }
.rname { font-weight: 600; font-size: 13px; }
.rwhen { font-size: 11px; color: var(--text-dim); }
.rt { font-size: 12px; color: var(--text); margin-top: 2px; }
.rs { font-size: 16px; font-weight: 700; }
.rs.done { color: var(--success); }
.rs.doing { color: #fcd34d; animation: pl 1.4s ease-in-out infinite; }
.rs.pending { color: var(--text-dim); }
@keyframes pl { 0%,100% { opacity: 1; } 50% { opacity: .4; } }

@media (max-width: 1024px) {
  .row { grid-template-columns: 1fr; }
  .dsr-row { grid-template-columns: 1fr 1fr; gap: 6px; }
}
</style>
