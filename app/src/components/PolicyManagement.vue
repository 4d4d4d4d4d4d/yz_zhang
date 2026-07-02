<script setup>
import { computed } from 'vue'

const policies = [
  { id: 'POL-001', name: 'Information Security Policy',  version: 'v4.2', updated: 'Nov 02 2025', expires: 'Nov 02 2026', ack: 98, owner: 'CISO', training: true },
  { id: 'POL-002', name: 'Acceptable Use Policy',         version: 'v3.1', updated: 'Oct 18 2025', expires: 'Oct 18 2026', ack: 96, owner: 'IT',   training: true },
  { id: 'POL-003', name: 'Data Classification & Handling', version: 'v2.4', updated: 'Sep 24 2025', expires: 'Sep 24 2026', ack: 92, owner: 'CISO', training: true },
  { id: 'POL-004', name: 'Vendor Risk Management',         version: 'v2.0', updated: 'Aug 10 2025', expires: 'Feb 10 2026', ack: 88, owner: 'Procurement', training: false },
  { id: 'POL-005', name: 'Incident Response Plan',         version: 'v3.0', updated: 'Nov 22 2025', expires: 'Nov 22 2026', ack: 94, owner: 'SRE',  training: true },
  { id: 'POL-006', name: 'Business Continuity & DR',       version: 'v2.2', updated: 'Jul 14 2025', expires: 'Jan 14 2026', ack: 82, owner: 'SRE',  training: false },
  { id: 'POL-007', name: 'AI Use & Generative Content',    version: 'v1.3', updated: 'Nov 28 2025', expires: 'May 28 2026', ack: 78, owner: 'AI Safety', training: true },
  { id: 'POL-008', name: 'Privacy Policy · Customer',      version: 'v5.1', updated: 'Oct 30 2025', expires: 'Oct 30 2026', ack: 100,owner: 'Privacy',  training: false }
]

const teams = ['Engineering', 'Sales', 'Marketing', 'CS', 'Finance', 'HR']
const matrix = [
  { team: 'Engineering', total: 142, completed: 138 },
  { team: 'Sales',       total:  86, completed:  82 },
  { team: 'Marketing',   total:  64, completed:  60 },
  { team: 'CS',          total:  72, completed:  68 },
  { team: 'Finance',     total:  28, completed:  26 },
  { team: 'HR',          total:  18, completed:  18 }
]

function daysTo(iso) {
  const d = new Date(iso)
  return Math.round((d - new Date()) / 86400000)
}
function expirySeverity(daysLeft) {
  if (daysLeft < 30) return 'soon'
  if (daysLeft < 90) return 'mid'
  return 'far'
}

const summary = computed(() => ({
  total: policies.length,
  expiring: policies.filter(p => daysTo(p.expires) < 90).length,
  avgAck: Math.round(policies.reduce((s, p) => s + p.ack, 0) / policies.length),
  withTraining: policies.filter(p => p.training).length
}))
</script>

<template>
  <div class="pm">
    <div class="card head">
      <div>
        <div class="kicker">Policy management</div>
        <h3>{{ policies.length }} policies · avg ack {{ summary.avgAck }}%</h3>
        <p class="meta">{{ summary.expiring }} expiring within 90 days · {{ summary.withTraining }} with mandatory training</p>
      </div>
    </div>

    <div class="cat-row">
      <div class="card cat ok">
        <div class="cn">{{ summary.avgAck }}%</div>
        <div class="cl">Average ack</div>
      </div>
      <div class="card cat warn">
        <div class="cn">{{ summary.expiring }}</div>
        <div class="cl">Expiring &lt; 90d</div>
      </div>
      <div class="card cat">
        <div class="cn">{{ summary.withTraining }}</div>
        <div class="cl">With training module</div>
      </div>
      <div class="card cat info">
        <div class="cn">410</div>
        <div class="cl">Employees in scope</div>
      </div>
    </div>

    <div class="card">
      <h3>Policies · {{ policies.length }}</h3>
      <table class="t">
        <thead>
          <tr>
            <th>Policy</th>
            <th>Owner</th>
            <th>Version</th>
            <th>Updated</th>
            <th>Expires</th>
            <th>Acknowledgment</th>
            <th>Training</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in policies" :key="p.id">
            <td>
              <div class="p-id">{{ p.id }}</div>
              <div class="p-name">{{ p.name }}</div>
            </td>
            <td class="dimc">{{ p.owner }}</td>
            <td><code class="ver">{{ p.version }}</code></td>
            <td class="dimc">{{ p.updated }}</td>
            <td>
              <span class="exp" :class="expirySeverity(daysTo(p.expires))">
                {{ p.expires }} <span class="dimc-i">({{ daysTo(p.expires) }}d)</span>
              </span>
            </td>
            <td>
              <div class="ack-row">
                <div class="ack-bar">
                  <div class="ack-fill" :class="p.ack >= 95 ? 'ok' : p.ack >= 85 ? 'warn' : 'risk'" :style="{ width: p.ack + '%' }"></div>
                </div>
                <span class="ack-num">{{ p.ack }}%</span>
              </div>
            </td>
            <td><span v-if="p.training" class="badge ok">✓ required</span><span v-else class="dimc-i">optional</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>Training attestation · by team</h3>
      <p class="meta">Annual security &amp; AI policy training. Required for all in-scope staff.</p>
      <div class="teams">
        <div v-for="t in matrix" :key="t.team" class="team">
          <div class="t-head">
            <span class="t-name">{{ t.team }}</span>
            <span class="t-meta">{{ t.completed }} / {{ t.total }}</span>
          </div>
          <div class="t-bar">
            <div class="t-fill" :class="t.completed / t.total >= 0.95 ? 'ok' : t.completed / t.total >= 0.85 ? 'warn' : 'risk'" :style="{ width: (t.completed / t.total * 100) + '%' }"></div>
          </div>
          <div class="t-pct">{{ Math.round(t.completed / t.total * 100) }}%</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pm { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.cat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.cat { padding: 16px 18px; border-left: 3px solid var(--border); }
.cat.ok { border-color: var(--success); }
.cat.warn { border-color: #fcd34d; }
.cat.info { border-color: var(--primary-2); }
.cn { font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.cl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.t { width: 100%; border-collapse: collapse; font-size: 12px; }
.t th { text-align: left; padding: 10px 8px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.t td { padding: 12px 8px; border-bottom: 1px dashed var(--border); }
.t td.dimc { color: var(--text-dim); }
.p-id { font-family: ui-monospace, monospace; color: var(--primary-2); font-weight: 700; font-size: 10px; margin-bottom: 2px; }
.p-name { font-size: 13px; font-weight: 600; }
.ver { background: var(--surface-2); padding: 1px 6px; border-radius: 4px; font-size: 10px; font-family: ui-monospace, monospace; }

.exp.soon { color: var(--danger); font-weight: 700; }
.exp.mid  { color: #fcd34d; font-weight: 600; }
.exp.far  { color: var(--text-dim); }
.dimc-i { color: var(--text-dim); font-size: 11px; }

.ack-row { display: flex; align-items: center; gap: 10px; }
.ack-bar { flex: 1; height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; min-width: 80px; }
.ack-fill { height: 100%; border-radius: 999px; }
.ack-fill.ok { background: var(--success); }
.ack-fill.warn { background: #fcd34d; }
.ack-fill.risk { background: var(--danger); }
.ack-num { font-weight: 800; font-variant-numeric: tabular-nums; font-size: 11px; min-width: 36px; text-align: right; }

.badge.ok { font-size: 10px; padding: 3px 8px; border-radius: 5px; background: rgba(52, 211, 153, .15); color: #6ee7b7; font-weight: 700; }

.teams { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 12px; }
.team { padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.t-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.t-name { font-weight: 700; font-size: 13px; }
.t-meta { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.t-bar { height: 8px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-bottom: 6px; }
.t-fill { height: 100%; border-radius: 999px; }
.t-fill.ok { background: var(--success); }
.t-fill.warn { background: #fcd34d; }
.t-fill.risk { background: var(--danger); }
.t-pct { text-align: right; font-weight: 800; font-size: 13px; font-variant-numeric: tabular-nums; }

@media (max-width: 1024px) {
  .cat-row { grid-template-columns: 1fr 1fr; }
  .teams { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 540px) {
  .teams { grid-template-columns: 1fr; }
}
</style>
