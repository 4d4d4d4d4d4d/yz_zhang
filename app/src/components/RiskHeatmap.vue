<script setup>
import { ref, computed } from 'vue'

const view = ref('inherent')

const risks = [
  { id: 'R-001', title: 'GDPR cross-border transfer breach',     cat: 'Privacy',  owner: 'Cobalt Legal',  i: { l: 4, p: 5 }, r: { l: 2, p: 5 }, controls: ['SCC', 'DPA', 'Encryption'] },
  { id: 'R-002', title: 'Generative ad with PII leak',           cat: 'AI',       owner: 'AI Safety',     i: { l: 4, p: 4 }, r: { l: 2, p: 4 }, controls: ['PII filter', 'Pre-render scan'] },
  { id: 'R-003', title: 'Trademark infringement in localized creative', cat: 'IP', owner: 'Legal',       i: { l: 3, p: 4 }, r: { l: 2, p: 3 }, controls: ['TM monitor', 'Review queue'] },
  { id: 'R-004', title: 'Vendor outage · cloud region failure',  cat: 'Ops',      owner: 'SRE',           i: { l: 3, p: 5 }, r: { l: 1, p: 4 }, controls: ['Multi-region', 'Runbook'] },
  { id: 'R-005', title: 'CCPA do-not-sell signal not honored',   cat: 'Privacy',  owner: 'Privacy',       i: { l: 3, p: 3 }, r: { l: 1, p: 3 }, controls: ['Auto-pipeline', 'Audit log'] },
  { id: 'R-006', title: 'C2PA signature stripped downstream',    cat: 'AI',       owner: 'AI Safety',     i: { l: 2, p: 3 }, r: { l: 1, p: 2 }, controls: ['Sign re-verify'] },
  { id: 'R-007', title: 'Exec phishing → SSO compromise',        cat: 'Security', owner: 'Security',      i: { l: 3, p: 5 }, r: { l: 1, p: 4 }, controls: ['WebAuthn', 'MFA'] },
  { id: 'R-008', title: 'Model drift unnoticed on US cohort',    cat: 'AI',       owner: 'ML Ops',        i: { l: 4, p: 3 }, r: { l: 2, p: 2 }, controls: ['Drift monitor', 'Rollback'] },
  { id: 'R-009', title: 'Distributor pricing leak via API',      cat: 'Commercial', owner: 'Eng',         i: { l: 2, p: 4 }, r: { l: 1, p: 3 }, controls: ['Rate limit', 'Scope check'] },
  { id: 'R-010', title: 'Training non-compliance · APPI',        cat: 'Privacy',  owner: 'HR',            i: { l: 2, p: 2 }, r: { l: 1, p: 2 }, controls: ['Annual training'] }
]

const selected = ref('R-001')

function cell(l, p) {
  return risks.filter(r => {
    const v = view.value === 'inherent' ? r.i : r.r
    return v.l === l && v.p === p
  })
}

function risk(l, p) { return l * p }
function severity(l, p) {
  const s = risk(l, p)
  if (s >= 16) return 'critical'
  if (s >= 12) return 'high'
  if (s >= 6) return 'med'
  return 'low'
}

const cur = computed(() => risks.find(r => r.id === selected.value))

const summary = computed(() => {
  const view_ = view.value === 'inherent' ? 'i' : 'r'
  const counts = { critical: 0, high: 0, med: 0, low: 0 }
  for (const r of risks) {
    counts[severity(r[view_].l, r[view_].p)]++
  }
  return counts
})

const movement = computed(() => {
  const reduced = risks.filter(r => (r.i.l * r.i.p) > (r.r.l * r.r.p)).length
  const avgRed = Math.round(
    risks.reduce((s, r) => s + (1 - (r.r.l * r.r.p) / (r.i.l * r.i.p)) * 100, 0) / risks.length
  )
  return { reduced, avgRed }
})
</script>

<template>
  <div class="hm">
    <div class="card head">
      <div>
        <div class="kicker">Risk register</div>
        <h3>{{ risks.length }} risks · {{ view === 'inherent' ? 'inherent' : 'residual' }} view</h3>
        <p class="meta">Toggle between inherent (no controls) and residual (after controls) posture.</p>
      </div>
      <div class="toggle">
        <button :class="{ on: view === 'inherent' }" @click="view = 'inherent'" type="button">Inherent</button>
        <button :class="{ on: view === 'residual' }" @click="view = 'residual'" type="button">Residual</button>
      </div>
    </div>

    <div class="row">
      <div class="card grid-card">
        <div class="g-meta">
          <span><span class="lg low"></span>low</span>
          <span><span class="lg med"></span>medium</span>
          <span><span class="lg high"></span>high</span>
          <span><span class="lg critical"></span>critical</span>
        </div>

        <div class="grid-wrap">
          <div class="y-axis"><span>Catastrophic</span><span>Major</span><span>Moderate</span><span>Minor</span><span>Negligible</span></div>
          <div class="grid5">
            <template v-for="p in [5,4,3,2,1]" :key="p">
              <div v-for="l in [1,2,3,4,5]" :key="`${l}-${p}`" class="cell" :class="severity(l, p)">
                <div v-for="r in cell(l, p)" :key="r.id"
                  class="bubble" :class="{ on: selected === r.id }"
                  @click="selected = r.id" :title="r.title">{{ r.id.split('-')[1] }}</div>
              </div>
            </template>
          </div>
        </div>
        <div class="x-axis">
          <span>Rare</span><span>Unlikely</span><span>Possible</span><span>Likely</span><span>Certain</span>
        </div>
        <div class="axis-lbl x">Likelihood →</div>
        <div class="axis-lbl y">↑ Impact</div>

        <div class="summary">
          <div><div class="s-num critical">{{ summary.critical }}</div><div class="s-lbl">Critical</div></div>
          <div><div class="s-num high">{{ summary.high }}</div><div class="s-lbl">High</div></div>
          <div><div class="s-num med">{{ summary.med }}</div><div class="s-lbl">Medium</div></div>
          <div><div class="s-num low">{{ summary.low }}</div><div class="s-lbl">Low</div></div>
          <div class="s-sep"></div>
          <div><div class="s-num">{{ movement.reduced }}</div><div class="s-lbl">Reduced</div></div>
          <div><div class="s-num grad-text">{{ movement.avgRed }}%</div><div class="s-lbl">Avg reduction</div></div>
        </div>
      </div>

      <div class="card detail">
        <div class="d-head">
          <span class="d-id">{{ cur.id }}</span>
          <span class="d-cat" :class="cur.cat.toLowerCase()">{{ cur.cat }}</span>
        </div>
        <h3>{{ cur.title }}</h3>
        <p class="d-owner">Owner · {{ cur.owner }}</p>

        <div class="movement">
          <div class="m-side">
            <div class="m-lbl">Inherent</div>
            <div class="m-val" :class="severity(cur.i.l, cur.i.p)">{{ cur.i.l * cur.i.p }}</div>
            <div class="m-sub">L{{ cur.i.l }} × I{{ cur.i.p }}</div>
          </div>
          <div class="m-arr">→</div>
          <div class="m-side">
            <div class="m-lbl">Residual</div>
            <div class="m-val" :class="severity(cur.r.l, cur.r.p)">{{ cur.r.l * cur.r.p }}</div>
            <div class="m-sub">L{{ cur.r.l }} × I{{ cur.r.p }}</div>
          </div>
          <div class="m-side">
            <div class="m-lbl">Δ</div>
            <div class="m-val ok">−{{ cur.i.l * cur.i.p - cur.r.l * cur.r.p }}</div>
            <div class="m-sub">reduction</div>
          </div>
        </div>

        <div class="kicker">Controls in place</div>
        <div class="controls">
          <span v-for="c in cur.controls" :key="c" class="ctl">✓ {{ c }}</span>
        </div>

        <div class="d-actions">
          <button class="btn btn-primary sm" type="button">Open mitigation plan</button>
          <button class="btn btn-ghost sm" type="button">Re-assess</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hm { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.toggle { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; }
.toggle button { padding: 6px 14px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 12px; font-weight: 600; }
.toggle button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; align-items: flex-start; }

.grid-card { padding: 20px; position: relative; }
.g-meta { display: flex; gap: 14px; font-size: 11px; color: var(--text-dim); margin-bottom: 12px; flex-wrap: wrap; }
.lg { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }
.lg.low { background: rgba(52, 211, 153, .4); }
.lg.med { background: rgba(251, 191, 36, .4); }
.lg.high { background: rgba(255, 122, 217, .4); }
.lg.critical { background: rgba(248, 113, 113, .4); }

.grid-wrap { display: grid; grid-template-columns: 90px 1fr; gap: 8px; }
.y-axis { display: flex; flex-direction: column; justify-content: space-between; padding: 4px 8px; text-align: right; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .04em; }
.grid5 { display: grid; grid-template-columns: repeat(5, 1fr); grid-template-rows: repeat(5, 1fr); gap: 4px; aspect-ratio: 5 / 4; }
.cell { border-radius: 6px; position: relative; padding: 4px; display: flex; flex-wrap: wrap; gap: 3px; align-content: flex-start; }
.cell.low { background: rgba(52, 211, 153, .12); }
.cell.med { background: rgba(251, 191, 36, .12); }
.cell.high { background: rgba(255, 122, 217, .15); }
.cell.critical { background: rgba(248, 113, 113, .18); }

.bubble { width: 26px; height: 26px; border-radius: 50%; background: var(--bg-2); border: 1.5px solid var(--text-dim); display: grid; place-items: center; font-size: 10px; font-weight: 800; cursor: pointer; transition: transform .15s; color: var(--text); }
.bubble:hover { transform: scale(1.1); }
.bubble.on { border-color: var(--primary-2); box-shadow: 0 0 0 2px rgba(34, 211, 238, .25); background: var(--primary-2); color: #0a0a0f; }

.x-axis { display: grid; grid-template-columns: repeat(5, 1fr); margin-left: 98px; margin-top: 8px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .04em; text-align: center; }

.axis-lbl { position: absolute; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; font-weight: 700; }
.axis-lbl.x { bottom: 14px; right: 24px; }
.axis-lbl.y { top: 60px; left: 12px; writing-mode: vertical-rl; transform: rotate(180deg); }

.summary { display: grid; grid-template-columns: repeat(6, 1fr) auto auto; gap: 14px; align-items: center; padding-top: 16px; margin-top: 18px; border-top: 1px solid var(--border); }
.summary > div:not(.s-sep) { text-align: center; }
.s-num { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.s-num.critical { color: #fca5a5; }
.s-num.high { color: #f5d0fe; }
.s-num.med { color: #fcd34d; }
.s-num.low { color: #6ee7b7; }
.s-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }
.s-sep { width: 1px; height: 36px; background: var(--border); margin: 0 4px; }

.detail { padding: 20px; }
.d-head { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
.d-id { font-family: ui-monospace, monospace; font-weight: 700; color: var(--primary-2); font-size: 12px; }
.d-cat { font-size: 10px; padding: 3px 8px; border-radius: 5px; text-transform: uppercase; letter-spacing: .05em; font-weight: 700; background: var(--surface-2); color: var(--text-dim); }
.d-cat.privacy { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.d-cat.ai { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.d-cat.security { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.d-cat.ip { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.d-cat.ops { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.d-owner { color: var(--text-dim); font-size: 12px; margin: 4px 0 18px; }

.movement { display: grid; grid-template-columns: 1fr auto 1fr 1fr; gap: 12px; align-items: center; padding: 16px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); margin-bottom: 18px; }
.m-side { text-align: center; }
.m-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-bottom: 4px; }
.m-val { font-size: 26px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; padding: 4px 10px; border-radius: 6px; display: inline-block; }
.m-val.low { background: rgba(52, 211, 153, .12); color: #6ee7b7; }
.m-val.med { background: rgba(251, 191, 36, .12); color: #fcd34d; }
.m-val.high { background: rgba(255, 122, 217, .15); color: #f5d0fe; }
.m-val.critical { background: rgba(248, 113, 113, .18); color: #fca5a5; }
.m-val.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.m-sub { font-size: 10px; color: var(--text-dim); margin-top: 4px; }
.m-arr { color: var(--text-dim); font-size: 18px; }

.controls { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 18px; }
.ctl { padding: 4px 10px; border-radius: 6px; background: rgba(52, 211, 153, .12); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, .3); font-size: 11px; }

.d-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

@media (max-width: 1024px) {
  .row { grid-template-columns: 1fr; }
  .summary { grid-template-columns: repeat(4, 1fr); }
  .s-sep { display: none; }
}
</style>
