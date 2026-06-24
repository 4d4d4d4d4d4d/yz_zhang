<script setup>
import { ref, computed } from 'vue'

const region = ref('all')
const regions = ['all', 'EU', 'US', 'JP', 'BR', 'SEA']

const frameworks = [
  { name: 'GDPR',   region: 'EU', status: 'pass', controls: 142, last: 'Nov 28', score: 96 },
  { name: 'CCPA / CPRA', region: 'US', status: 'pass', controls: 88, last: 'Nov 22', score: 94 },
  { name: 'APPI',   region: 'JP', status: 'pass', controls: 64, last: 'Dec 01', score: 92 },
  { name: 'LGPD',   region: 'BR', status: 'warn', controls: 71, last: 'Oct 12', score: 78 },
  { name: 'PDPA',   region: 'SEA', status: 'pass', controls: 58, last: 'Nov 04', score: 89 },
  { name: 'DSA',    region: 'EU', status: 'warn', controls: 47, last: 'Nov 30', score: 81 },
  { name: 'C2PA provenance', region: 'all', status: 'pass', controls: 12, last: 'Dec 01', score: 100 },
  { name: 'AI Act readiness', region: 'EU', status: 'risk', controls: 38, last: 'Oct 02', score: 64 }
]

const filtered = computed(() => region.value === 'all' ? frameworks : frameworks.filter(f => f.region === region.value || f.region === 'all'))
const overall = computed(() => Math.round(filtered.value.reduce((s, f) => s + f.score, 0) / filtered.value.length))

const risks = [
  { sev: 'high',   title: 'Brazil LGPD: cross-border data transfer lacks SCC', area: 'Data', owner: 'Cobalt Legal', eta: 'Dec 12' },
  { sev: 'high',   title: 'EU AI Act: high-risk classification for generative ads pending review', area: 'AI', owner: 'Compliance', eta: 'Dec 20' },
  { sev: 'med',    title: 'DSA: trusted-flagger workflow not yet documented', area: 'Content', owner: 'Trust & Safety', eta: 'Dec 15' },
  { sev: 'med',    title: 'CCPA: opt-out signal integration on partner CRM', area: 'Privacy', owner: 'Engineering', eta: 'Dec 10' },
  { sev: 'low',    title: 'APPI: annual training overdue for 3 staff', area: 'People', owner: 'HR', eta: 'Dec 06' }
]

const docs = [
  { name: 'Master Service Agreement', type: 'MSA', version: 'v4.2', langs: 'EN · JA · ZH · ES · DE · PT', size: '218 KB' },
  { name: 'Data Processing Agreement', type: 'DPA', version: 'v3.1', langs: 'EN · JA · DE · PT', size: '142 KB' },
  { name: 'Mutual NDA', type: 'NDA', version: 'v2.0', langs: 'EN · JA · ZH · DE', size: '86 KB' },
  { name: 'Brand Asset License', type: 'License', version: 'v1.4', langs: 'EN · JA · ES', size: '64 KB' },
  { name: 'AI Content Provenance Policy', type: 'Policy', version: 'v1.0', langs: 'EN', size: '40 KB' },
  { name: 'GDPR SCC Module Two', type: 'Annex', version: '2021/914', langs: 'EN · DE · FR', size: '128 KB' }
]

const scanning = ref(false)
const scanResult = ref(null)
async function scan() {
  scanning.value = true; scanResult.value = null
  await new Promise(r => setTimeout(r, 1100))
  scanResult.value = {
    score: 78,
    findings: [
      { sev: 'high', text: 'Generative voice cloning consent not captured for JP voice talent.' },
      { sev: 'med',  text: 'Disclosure copy missing AI-generated tag in 4 of 24 variants.' },
      { sev: 'low',  text: 'Brand-safety check did not run on 2 variants — re-queue.' },
      { sev: 'ok',   text: 'C2PA signatures present on 24/24 outputs.' },
      { sev: 'ok',   text: 'GDPR / APPI / CCPA disclosures embedded in landing page.' }
    ]
  }
  scanning.value = false
}

const audit = [
  { who: 'Auto-policy', what: 'Quarterly GDPR control evidence collected', when: '2 hours ago' },
  { who: 'Akiko Mori',  what: 'Approved updated DPA v3.1 for JP partners',  when: '5 hours ago' },
  { who: 'Auto-policy', what: 'CCPA Do-Not-Sell signal honored on 1,284 sessions', when: 'Yesterday' },
  { who: 'Cobalt Legal', what: 'Filed redline of partner MSA · clauses 4.2, 7.1', when: '2 days ago' },
  { who: 'Auto-policy', what: 'C2PA signatures regenerated for 142 renders', when: '3 days ago' }
]
</script>

<template>
  <div class="trust">
    <div class="card overview">
      <div class="ov-left">
        <div class="kicker">Posture</div>
        <div class="big grad-text">{{ overall }}<span class="of">/100</span></div>
        <div class="sub">Overall trust score · {{ region === 'all' ? 'all regions' : region }}</div>
        <div class="legend">
          <span class="lg pass">✓ {{ frameworks.filter(f => f.status === 'pass').length }} passing</span>
          <span class="lg warn">! {{ frameworks.filter(f => f.status === 'warn').length }} caution</span>
          <span class="lg risk">▲ {{ frameworks.filter(f => f.status === 'risk').length }} at risk</span>
        </div>
      </div>
      <div class="ov-right">
        <div class="region">
          <button v-for="r in regions" :key="r" :class="{ on: region === r }" @click="region = r" type="button">{{ r === 'all' ? 'All' : r }}</button>
        </div>
        <div class="fw-grid">
          <div v-for="f in filtered" :key="f.name" class="fw">
            <div class="fw-head">
              <span class="fw-name">{{ f.name }}</span>
              <span class="fw-status" :class="f.status">{{ f.status === 'pass' ? 'PASS' : f.status === 'warn' ? 'CAUTION' : 'RISK' }}</span>
            </div>
            <div class="fw-meta">{{ f.region }} · {{ f.controls }} controls · last audit {{ f.last }}</div>
            <div class="fw-bt"><div class="fw-bf" :style="{ width: f.score + '%' }" :class="f.status"></div></div>
          </div>
        </div>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <div class="h-row">
          <h3>Active risks</h3>
          <span class="meta">{{ risks.length }} open</span>
        </div>
        <table class="risks">
          <thead>
            <tr><th>Severity</th><th>Risk</th><th>Owner</th><th>ETA</th></tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in risks" :key="i">
              <td><span class="sev" :class="r.sev">{{ r.sev.toUpperCase() }}</span></td>
              <td>
                <div class="rt">{{ r.title }}</div>
                <div class="ra">{{ r.area }}</div>
              </td>
              <td>{{ r.owner }}</td>
              <td>{{ r.eta }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>AI risk review</h3>
        <p class="rrp">Scan the current campaign &amp; deal for legal, brand-safety and AI-disclosure risks before going live.</p>
        <button class="btn btn-primary" :disabled="scanning" @click="scan" type="button">
          <span v-if="scanning">Scanning…</span>
          <span v-else-if="scanResult">Re-run scan</span>
          <span v-else>Run scan</span>
        </button>
        <div v-if="scanResult" class="scan">
          <div class="scan-head">
            <div>
              <div class="ss-score" :class="scanResult.score >= 90 ? 'ok' : scanResult.score >= 75 ? 'warn' : 'risk'">{{ scanResult.score }}</div>
              <div class="ss-lbl">Risk score</div>
            </div>
            <div class="scan-summary">
              {{ scanResult.findings.filter(f => f.sev === 'high').length }} high ·
              {{ scanResult.findings.filter(f => f.sev === 'med').length }} medium ·
              {{ scanResult.findings.filter(f => f.sev === 'low').length }} low
            </div>
          </div>
          <ul>
            <li v-for="(f, i) in scanResult.findings" :key="i" :class="f.sev">
              <span class="sev-tag" :class="f.sev">{{ f.sev === 'ok' ? '✓' : f.sev.toUpperCase() }}</span>
              <span>{{ f.text }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="h-row">
        <h3>Document repository</h3>
        <button class="btn btn-ghost sm" type="button">Upload template</button>
      </div>
      <div class="docs">
        <div v-for="d in docs" :key="d.name" class="doc">
          <div class="d-icon">📄</div>
          <div class="d-body">
            <div class="d-name">{{ d.name }}</div>
            <div class="d-meta">{{ d.type }} · {{ d.version }} · {{ d.size }}</div>
            <div class="d-langs">{{ d.langs }}</div>
          </div>
          <button class="mini" type="button">Download</button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="h-row">
        <h3>Audit log</h3>
        <span class="meta">Last 5 events</span>
      </div>
      <ul class="audit">
        <li v-for="(a, i) in audit" :key="i">
          <span class="awho">{{ a.who }}</span>
          <span class="awhat">{{ a.what }}</span>
          <span class="awhen">{{ a.when }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.trust { display: flex; flex-direction: column; gap: 20px; }
.overview { padding: 24px; display: grid; grid-template-columns: 280px 1fr; gap: 32px; }
.kicker { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.big { font-size: 72px; font-weight: 800; line-height: 1; margin: 8px 0; font-variant-numeric: tabular-nums; }
.of { font-size: 24px; color: var(--text-dim); }
.sub { color: var(--text-dim); }
.legend { display: flex; flex-direction: column; gap: 8px; margin-top: 18px; }
.lg { font-size: 12px; }
.lg.pass { color: var(--success); }
.lg.warn { color: #fcd34d; }
.lg.risk { color: var(--danger); }

.region { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; margin-bottom: 16px; }
.region button { padding: 6px 12px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 12px; }
.region button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }
.fw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.fw { padding: 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.fw-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.fw-name { font-weight: 600; font-size: 14px; }
.fw-status { font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 700; letter-spacing: .06em; }
.fw-status.pass { background: rgba(52,211,153,.15); color: #6ee7b7; }
.fw-status.warn { background: rgba(251,191,36,.15); color: #fcd34d; }
.fw-status.risk { background: rgba(248,113,113,.15); color: #fca5a5; }
.fw-meta { font-size: 11px; color: var(--text-dim); margin-bottom: 8px; }
.fw-bt { height: 4px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.fw-bf { height: 100%; }
.fw-bf.pass { background: var(--success); }
.fw-bf.warn { background: #fcd34d; }
.fw-bf.risk { background: var(--danger); }

.row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; }
.h-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.meta { color: var(--text-dim); font-size: 12px; }

.risks { width: 100%; border-collapse: collapse; font-size: 13px; }
.risks th { text-align: left; padding: 10px 8px; font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; border-bottom: 1px solid var(--border); font-weight: 600; }
.risks td { padding: 12px 8px; border-bottom: 1px dashed var(--border); vertical-align: top; }
.risks tr:last-child td { border-bottom: 0; }
.sev { font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 700; letter-spacing: .06em; }
.sev.high { background: rgba(248,113,113,.15); color: #fca5a5; }
.sev.med  { background: rgba(251,191,36,.15); color: #fcd34d; }
.sev.low  { background: rgba(96,165,250,.15); color: #93c5fd; }
.rt { font-weight: 500; }
.ra { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

.rrp { color: var(--text-dim); margin: 0 0 14px; }
.scan { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
.scan-head { display: flex; align-items: center; gap: 20px; margin-bottom: 12px; }
.ss-score { font-size: 36px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.ss-score.ok { color: var(--success); }
.ss-score.warn { color: #fcd34d; }
.ss-score.risk { color: var(--danger); }
.ss-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }
.scan-summary { color: var(--text-dim); font-size: 13px; }
.scan ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.scan li { display: flex; gap: 10px; align-items: flex-start; font-size: 13px; padding: 8px 10px; border-radius: 8px; background: var(--surface); }
.scan li.ok { background: rgba(52, 211, 153, .08); }
.scan li.high { background: rgba(248, 113, 113, .08); }
.sev-tag { padding: 2px 7px; border-radius: 5px; font-size: 10px; font-weight: 700; flex-shrink: 0; }
.sev-tag.high { background: rgba(248,113,113,.2); color: #fca5a5; }
.sev-tag.med  { background: rgba(251,191,36,.2); color: #fcd34d; }
.sev-tag.low  { background: rgba(96,165,250,.2); color: #93c5fd; }
.sev-tag.ok   { background: rgba(52,211,153,.2); color: #6ee7b7; }

.docs { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.doc { display: flex; align-items: center; gap: 14px; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.d-icon { font-size: 22px; }
.d-body { flex: 1; min-width: 0; }
.d-name { font-weight: 600; font-size: 14px; }
.d-meta { font-size: 11px; color: var(--text-dim); }
.d-langs { font-size: 11px; color: var(--text); margin-top: 2px; }
.mini { padding: 6px 12px; border-radius: 8px; background: var(--surface-2); border: 1px solid var(--border); color: var(--text); font-size: 12px; cursor: pointer; }
.mini:hover { border-color: var(--primary); }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.audit { list-style: none; padding: 0; margin: 0; }
.audit li { display: grid; grid-template-columns: 180px 1fr 120px; gap: 16px; padding: 12px 8px; border-bottom: 1px dashed var(--border); font-size: 13px; }
.audit li:last-child { border-bottom: 0; }
.awho { color: var(--primary-2); font-weight: 600; }
.awhat { color: var(--text); }
.awhen { color: var(--text-dim); text-align: right; font-size: 12px; }

@media (max-width: 1024px) {
  .overview { grid-template-columns: 1fr; }
  .row { grid-template-columns: 1fr; }
  .fw-grid { grid-template-columns: 1fr; }
  .docs { grid-template-columns: 1fr; }
  .audit li { grid-template-columns: 1fr; gap: 4px; }
  .awhen { text-align: left; }
}
</style>
