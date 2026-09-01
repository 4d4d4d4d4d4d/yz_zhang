<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { posture, STATUS_CAP } from '../logic/posture.js'

const { t } = useI18n()

const region = ref('all')
const regions = ['all', 'EU', 'US', 'JP', 'BR', 'SEA']

const frameworks = [
  { key: 'gdpr', name: 'GDPR',   region: 'EU', status: 'pass', controls: 142, last: 'Nov 28', score: 96 },
  { key: 'ccpa', name: 'CCPA / CPRA', region: 'US', status: 'pass', controls: 88, last: 'Nov 22', score: 94 },
  { key: 'appi', name: 'APPI',   region: 'JP', status: 'pass', controls: 64, last: 'Dec 01', score: 92 },
  { key: 'lgpd', name: 'LGPD',   region: 'BR', status: 'warn', controls: 71, last: 'Oct 12', score: 78 },
  { key: 'pdpa', name: 'PDPA',   region: 'SEA', status: 'pass', controls: 58, last: 'Nov 04', score: 89 },
  { key: 'dsa',  name: 'DSA',    region: 'EU', status: 'warn', controls: 47, last: 'Nov 30', score: 81 },
  { key: 'c2pa', name: 'C2PA provenance', region: 'all', status: 'pass', controls: 12, last: 'Dec 01', score: 100 },
  { key: 'aiact', name: 'AI Act readiness', region: 'EU', status: 'risk', controls: 38, last: 'Oct 02', score: 64 }
]

// `scope` ties each finding to the regime it belongs to, so a Brazilian gap
// stops being charged against the EU posture (spec 61).
const risks = [
  { key: 'lgpdScc',  sev: 'high', scope: 'BR', area: 'data',    owner: 'Cobalt Legal',   eta: 'Dec 12' },
  { key: 'aiAct',    sev: 'high', scope: 'EU', area: 'ai',      owner: 'Compliance',     eta: 'Dec 20' },
  { key: 'dsaFlag',  sev: 'med',  scope: 'EU', area: 'content', owner: 'Trust & Safety', eta: 'Dec 15' },
  { key: 'ccpaOpt',  sev: 'med',  scope: 'US', area: 'privacy', owner: 'Engineering',    eta: 'Dec 10' },
  { key: 'appiTrn',  sev: 'low',  scope: 'JP', area: 'people',  owner: 'HR',             eta: 'Dec 06' }
]

const report = computed(() => posture(frameworks, { scope: region.value, risks }))
const visible = computed(() => [...report.value.frameworks, ...report.value.global])
const scopedRisks = computed(() => report.value.openRisks)

const docs = [
  { key: 'msa',     type: 'MSA', version: 'v4.2', langs: 'EN · JA · ZH · ES · DE · PT', size: '218 KB' },
  { key: 'dpa',     type: 'DPA', version: 'v3.1', langs: 'EN · JA · DE · PT', size: '142 KB' },
  { key: 'nda',     type: 'NDA', version: 'v2.0', langs: 'EN · JA · ZH · DE', size: '86 KB' },
  { key: 'license', type: 'License', version: 'v1.4', langs: 'EN · JA · ES', size: '64 KB' },
  { key: 'prov',    type: 'Policy', version: 'v1.0', langs: 'EN', size: '40 KB' },
  { key: 'scc',     type: 'Annex', version: '2021/914', langs: 'EN · DE · FR', size: '128 KB' }
]

// Spec 61 — the scan used to return a fixed 78 and the same five findings no
// matter what was on screen, which is a claim about analysis that never
// happened. It is now derived from the posture actually in scope: the same
// engine, the same numbers, so the two cards cannot contradict each other.
const scanning = ref(false)
const scanned = ref(null)
async function scan() {
  scanning.value = true
  scanned.value = null
  await new Promise(r => setTimeout(r, 700))
  const r = report.value
  scanned.value = {
    score: r.covered ? r.score : null,
    scope: region.value,
    findings: [
      ...(r.capped && r.worst
        ? [{ sev: r.worst.status === 'risk' ? 'high' : 'med', id: 'capped',
             args: { framework: r.worst.name, raw: r.raw, cap: r.cap } }]
        : []),
      ...r.openRisks.map(x => ({ sev: x.sev, id: 'risk', args: { title: t(`trustc.risk.${x.key}`), owner: x.owner, eta: x.eta } })),
      ...(r.deduction.capped
        ? [{ sev: 'med', id: 'tail', args: { gross: r.deduction.gross, applied: r.deduction.applied } }]
        : []),
      ...(r.global.length
        ? [{ sev: 'ok', id: 'global', args: { list: r.global.map(f => f.name).join(', ') } }]
        : []),
      ...(r.counts.pass && !r.counts.risk
        ? [{ sev: 'ok', id: 'clean', args: { n: r.counts.pass } }]
        : [])
    ]
  }
  scanning.value = false
}

const audit = [
  { key: 'evidence', who: 'Auto-policy',  when: '2h' },
  { key: 'dpa',      who: 'Akiko Mori',   when: '5h' },
  { key: 'dns',      who: 'Auto-policy',  when: '1d' },
  { key: 'redline',  who: 'Cobalt Legal', when: '2d' },
  { key: 'c2pa',     who: 'Auto-policy',  when: '3d' }
]
</script>

<template>
  <div class="trust">
    <div class="card overview">
      <div class="ov-left">
        <div class="kicker">{{ t('trustc.posture') }}</div>
        <template v-if="report.covered">
          <div class="big grad-text">{{ report.score }}<span class="of">/100</span></div>
          <div class="sub">{{ t('trustc.scoreSub', {
            scope: region === 'all' ? t('trustc.allRegions') : region,
            controls: report.controls
          }) }}</div>
        </template>
        <template v-else>
          <div class="big none">—</div>
          <div class="sub">{{ t('trustc.noCoverage', { scope: region }) }}</div>
        </template>

        <!-- Every adjustment between the control-weighted number and the
             headline is stated, so the score is arguable rather than asserted. -->
        <ul v-if="report.covered" class="calc">
          <li><span>{{ t('trustc.weighted') }}</span><strong>{{ report.raw }}</strong></li>
          <li v-if="report.capped" class="cap">
            <span>{{ t('trustc.cappedBy', { framework: report.worst.name }) }}</span>
            <strong>≤ {{ report.cap }}</strong>
          </li>
          <li v-if="report.deduction.applied">
            <span>{{ t('trustc.openFindings', { n: report.openRisks.length }) }}</span>
            <strong>−{{ report.deduction.applied }}</strong>
          </li>
        </ul>

        <div v-if="report.covered" class="legend">
          <span class="lg pass">✓ {{ t('trustc.passing', { n: report.counts.pass }) }}</span>
          <span class="lg warn">! {{ t('trustc.caution', { n: report.counts.warn }) }}</span>
          <span class="lg risk">▲ {{ t('trustc.atRisk', { n: report.counts.risk }) }}</span>
        </div>
      </div>
      <div class="ov-right">
        <div class="region" role="group" :aria-label="t('trustc.regionFilter')">
          <button v-for="r in regions" :key="r" :class="{ on: region === r }" @click="region = r"
            type="button" :aria-pressed="region === r">{{ r === 'all' ? t('trustc.all') : r }}</button>
        </div>
        <div class="fw-grid">
          <div v-for="f in visible" :key="f.key" class="fw" :class="{ ghost: f.region === 'all' && region !== 'all' }">
            <div class="fw-head">
              <span class="fw-name">{{ f.name }}</span>
              <span class="fw-status" :class="f.status">{{ t(`trustc.status.${f.status}`) }}</span>
            </div>
            <div class="fw-meta">
              {{ f.region }} · {{ t('trustc.controls', { n: f.controls }) }} · {{ t('trustc.lastAudit', { date: f.last }) }}
              <span v-if="f.region === 'all' && region !== 'all'" class="ghost-tag">{{ t('trustc.globalNote') }}</span>
            </div>
            <div class="fw-bt"><div class="fw-bf" :style="{ width: f.score + '%' }" :class="f.status"></div></div>
          </div>
        </div>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <div class="h-row">
          <h3>{{ t('trustc.activeRisks') }}</h3>
          <span class="meta">{{ t('trustc.openN', { n: scopedRisks.length }) }}</span>
        </div>
        <table class="risks">
          <thead>
            <tr>
              <th>{{ t('trustc.colSeverity') }}</th><th>{{ t('trustc.colRisk') }}</th>
              <th>{{ t('trustc.colOwner') }}</th><th>{{ t('trustc.colEta') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in scopedRisks" :key="r.key">
              <td><span class="sev" :class="r.sev">{{ t(`trustc.sev.${r.sev}`) }}</span></td>
              <td>
                <div class="rt">{{ t(`trustc.risk.${r.key}`) }}</div>
                <div class="ra">{{ t(`trustc.area.${r.area}`) }} · −{{ { high: 6, med: 3, low: 1 }[r.sev] }}</div>
              </td>
              <td>{{ r.owner }}</td>
              <td>{{ r.eta }}</td>
            </tr>
            <tr v-if="!scopedRisks.length"><td colspan="4" class="empty">{{ t('trustc.noRisks') }}</td></tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>{{ t('trustc.aiReview') }}</h3>
        <p class="rrp">{{ t('trustc.aiReviewSub') }}</p>
        <button class="btn btn-primary" :disabled="scanning" @click="scan" type="button">
          <span v-if="scanning">{{ t('trustc.scanning') }}</span>
          <span v-else-if="scanned">{{ t('trustc.rescan') }}</span>
          <span v-else>{{ t('trustc.runScan') }}</span>
        </button>
        <div v-if="scanned" class="scan">
          <div class="scan-head">
            <div>
              <div class="ss-score" :class="scanned.score === null ? 'risk' : scanned.score >= 90 ? 'ok' : scanned.score >= 75 ? 'warn' : 'risk'">
                {{ scanned.score === null ? '—' : scanned.score }}
              </div>
              <div class="ss-lbl">{{ t('trustc.riskScore') }}</div>
            </div>
            <div class="scan-summary">
              {{ t('trustc.scanSummary', {
                high: scanned.findings.filter(f => f.sev === 'high').length,
                med: scanned.findings.filter(f => f.sev === 'med').length,
                low: scanned.findings.filter(f => f.sev === 'low').length
              }) }}
            </div>
          </div>
          <ul>
            <li v-for="(f, i) in scanned.findings" :key="i" :class="f.sev">
              <span class="sev-tag" :class="f.sev">{{ f.sev === 'ok' ? '✓' : t(`trustc.sev.${f.sev}`) }}</span>
              <span>{{ t(`trustc.finding.${f.id}`, f.args) }}</span>
            </li>
            <li v-if="!scanned.findings.length" class="ok">
              <span class="sev-tag ok">✓</span><span>{{ t('trustc.finding.none') }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="h-row">
        <h3>{{ t('trustc.docs') }}</h3>
        <button class="btn btn-ghost sm" type="button">{{ t('trustc.upload') }}</button>
      </div>
      <div class="docs">
        <div v-for="d in docs" :key="d.key" class="doc">
          <div class="d-icon" aria-hidden="true">📄</div>
          <div class="d-body">
            <div class="d-name">{{ t(`trustc.doc.${d.key}`) }}</div>
            <div class="d-meta">{{ d.type }} · {{ d.version }} · {{ d.size }}</div>
            <div class="d-langs">{{ d.langs }}</div>
          </div>
          <button class="mini" type="button" :aria-label="t('trustc.downloadFile', { name: t(`trustc.doc.${d.key}`) })">{{ t('trustc.download') }}</button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="h-row">
        <h3>{{ t('trustc.auditLog') }}</h3>
        <span class="meta">{{ t('trustc.lastN', { n: audit.length }) }}</span>
      </div>
      <ul class="audit">
        <li v-for="a in audit" :key="a.key">
          <span class="awho">{{ a.who }}</span>
          <span class="awhat">{{ t(`trustc.audit.${a.key}`) }}</span>
          <span class="awhen">{{ t('trustc.ago', { t: a.when }) }}</span>
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
.big.none { color: var(--text-dim); }
.calc { list-style: none; margin: 14px 0 0; padding: 12px 0 0; border-top: 1px solid var(--border); }
.calc li { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; color: var(--text-dim); padding: 3px 0; }
.calc li strong { color: var(--text); font-variant-numeric: tabular-nums; }
.calc li.cap strong { color: #fcd34d; }
.fw.ghost { opacity: .62; border-style: dashed; }
.ghost-tag { display: inline-block; margin-left: 6px; font-size: 9px; text-transform: uppercase; letter-spacing: .06em;
  padding: 1px 5px; border-radius: 4px; background: var(--bg-2); color: var(--text-dim); }
.empty { color: var(--text-dim); font-size: 12px; padding: 14px 0; text-align: center; }
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
