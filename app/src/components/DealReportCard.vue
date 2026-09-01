<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { dealReadinessSnapshot } from '../store/workspace.js'
import { buildDealReport } from '../logic/dealReport.js'

// Spec 34 — the exportable deal one-pager. Reads the single-source workspace
// readiness (same engine the notification bell uses) and renders a printable,
// copyable readiness verdict for sharing with a cross-border partner.
const { t, d, locale } = useI18n()

// Frozen at mount so the printed/copied timestamp is stable for a given view.
const now = Date.now()
const report = computed(() => buildDealReport(dealReadinessSnapshot(), { now }))

const VERDICT_CLASS = { ready: 'ok', blocked: 'bad', progress: 'wip' }

function fmtDate(ts) {
  try {
    return new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(ts)
  } catch { return new Date(ts).toISOString() }
}

// Localized plain-text one-pager for the clipboard.
function shareText() {
  const r = report.value
  const lines = [
    `${t('report.title')} · ${r.id}`,
    `${t('report.verdict')}: ${t('report.v.' + r.verdict)} (${r.score}/100)`,
    `${t('report.progress', { done: r.complete, total: r.total })}`,
    ''
  ]
  for (const s of r.stages) {
    lines.push(`- ${t('report.stage.' + s.stage)}: ${t('report.status.' + s.status)}`)
  }
  if (r.blockers.length) {
    lines.push('', `${t('report.blockers')}:`)
    for (const b of r.blockers) lines.push(`- [${t('report.sev.' + b.severity)}] ${b.action}`)
  }
  lines.push('', `${t('report.generated')}: ${fmtDate(r.generatedAt)}`)
  return lines.join('\n')
}

const copied = ref(false)
async function copy() {
  try {
    await navigator.clipboard.writeText(shareText())
    copied.value = true
    setTimeout(() => { copied.value = false }, 1800)
  } catch { /* clipboard unavailable — the print path still works */ }
}

function print() {
  if (typeof window !== 'undefined' && window.print) window.print()
}
</script>

<template>
  <div class="deal-report">
    <div class="card dr-head">
      <div>
        <div class="kicker">{{ t('report.kicker') }}</div>
        <h3>{{ t('report.title') }} · {{ report.id }}</h3>
        <p class="meta">{{ t('report.sub') }}</p>
      </div>
      <div class="dr-actions">
        <button type="button" class="btn ghost" @click="copy">{{ copied ? t('report.copied') : t('report.copy') }}</button>
        <button type="button" class="btn" @click="print">{{ t('report.print') }}</button>
      </div>
    </div>

    <div class="card dr-verdict" :class="VERDICT_CLASS[report.verdict]">
      <div class="dv-badge">{{ t('report.v.' + report.verdict) }}</div>
      <div class="dv-score">{{ report.score }}<span>/100</span></div>
      <div class="dv-prog">{{ t('report.progress', { done: report.complete, total: report.total }) }}</div>
    </div>

    <div class="card">
      <h3>{{ t('report.stages') }}</h3>
      <ul class="dr-stages">
        <li v-for="s in report.stages" :key="s.stage" class="ds" :class="s.status">
          <span class="ds-dot" aria-hidden="true"></span>
          <span class="ds-name">{{ t('report.stage.' + s.stage) }}</span>
          <span class="ds-status">{{ t('report.status.' + s.status) }}</span>
        </li>
      </ul>
    </div>

    <div class="card" v-if="report.blockers.length">
      <h3>{{ t('report.blockers') }}</h3>
      <ul class="dr-blockers">
        <li v-for="(b, i) in report.blockers" :key="i" class="db">
          <span class="db-sev" :class="b.severity">{{ t('report.sev.' + b.severity) }}</span>
          <span class="db-action">{{ b.action }}</span>
        </li>
      </ul>
    </div>

    <p class="dr-foot">{{ t('report.generated') }}: {{ fmtDate(report.generatedAt) }}</p>
  </div>
</template>

<style scoped>
.deal-report { display: flex; flex-direction: column; gap: 16px; }
.dr-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 18px 20px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.dr-actions { display: flex; gap: 8px; flex-shrink: 0; }
.btn { border: 1px solid var(--primary); background: var(--primary); color: #fff; border-radius: 9px; padding: 8px 14px; font-size: 13px; font-weight: 700; cursor: pointer; }
.btn.ghost { background: var(--surface); color: var(--text); border-color: var(--border); }
.btn:hover { filter: brightness(1.05); }

.dr-verdict { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 18px; padding: 20px; border-left: 4px solid var(--text-dim); }
.dr-verdict.ok { border-left-color: var(--success); }
.dr-verdict.bad { border-left-color: var(--danger); }
.dr-verdict.wip { border-left-color: var(--primary); }
.dv-badge { font-size: 13px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; padding: 6px 12px; border-radius: 999px; background: var(--surface-2); }
.dr-verdict.ok .dv-badge { color: var(--success); }
.dr-verdict.bad .dv-badge { color: var(--danger); }
.dr-verdict.wip .dv-badge { color: var(--primary); }
.dv-score { font-size: 34px; font-weight: 800; font-variant-numeric: tabular-nums; text-align: right; }
.dv-score span { font-size: 15px; color: var(--text-dim); font-weight: 600; }
.dv-prog { font-size: 12px; color: var(--text-dim); }

.dr-stages { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.ds { display: grid; grid-template-columns: 14px 1fr auto; align-items: center; gap: 10px; padding: 8px 4px; border-bottom: 1px solid rgba(255,255,255,.04); font-size: 13.5px; }
.ds-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--text-dim); }
.ds.complete .ds-dot { background: var(--success); }
.ds.partial .ds-dot { background: var(--primary); }
.ds.open .ds-dot { background: var(--danger); }
.ds-status { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .05em; }

.dr-blockers { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.db { display: flex; gap: 10px; align-items: flex-start; font-size: 13px; }
.db-sev { flex-shrink: 0; font-size: 10px; font-weight: 800; text-transform: uppercase; padding: 2px 8px; border-radius: 6px; background: var(--surface-2); }
.db-sev.zero { color: var(--danger); }
.db-sev.half { color: var(--primary); }
.dr-foot { font-size: 11px; color: var(--text-dim); margin: 0; }

@media (max-width: 540px) {
  .dr-head { flex-direction: column; }
  .dr-verdict { grid-template-columns: 1fr; text-align: left; }
  .dv-score { text-align: left; }
}
</style>

<!-- Print isolation (global, non-scoped): when printing, show ONLY the report
     one-pager, not the console shell. The visibility trick works regardless of
     the SPA layout above it. -->
<style>
@media print {
  body * { visibility: hidden; }
  .deal-report, .deal-report * { visibility: visible; }
  .deal-report { position: absolute; left: 0; top: 0; width: 100%; }
  .deal-report .dr-actions { display: none; }
}
</style>
