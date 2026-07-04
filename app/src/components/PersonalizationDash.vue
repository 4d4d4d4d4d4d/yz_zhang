<script setup>
import { ref, computed } from 'vue'

const tenants = [
  { id: 'lumi',   name: 'Lumi DTC',         logo: 'L' },
  { id: 'kaito',  name: 'Kaito Beauty',     logo: 'K' },
  { id: 'aurora', name: 'Aurora Media',     logo: 'A' }
]
const tenant = ref('lumi')

const data = {
  lumi: {
    kpis: { ctr_lift: 28.4, cvr_lift: 22.1, revenue_attr: 184000, rec_share: 38 },
    concepts: [
      { name: 'Lumi · UGC reel JP', impressions: 480000, ctr: 5.4, cvr: 3.2, rev: 64200 },
      { name: 'Lumi · Founder POV',  impressions: 340000, ctr: 4.1, cvr: 2.8, rev: 38500 },
      { name: 'Lumi · 7-day diary',  impressions: 286000, ctr: 4.8, cvr: 3.0, rev: 41800 }
    ],
    teams: [
      { name: 'Growth',    members: 6, jobs: 1248 },
      { name: 'Creative',  members: 8, jobs: 2640 },
      { name: 'Brand',     members: 3, jobs: 380 },
      { name: 'Agency',    members: 4, jobs: 920 }
    ]
  },
  kaito: {
    kpis: { ctr_lift: 18.2, cvr_lift: 14.8, revenue_attr: 42800, rec_share: 26 },
    concepts: [
      { name: 'Kaito · ASMR unbox',  impressions: 142000, ctr: 4.6, cvr: 2.2, rev: 14400 },
      { name: 'Kaito · Skin diary',  impressions: 98000,  ctr: 4.0, cvr: 2.6, rev: 10800 },
      { name: 'Kaito · 3-sec hero',  impressions: 82000,  ctr: 3.8, cvr: 1.9, rev: 7600 }
    ],
    teams: [
      { name: 'Growth',    members: 2, jobs: 380 },
      { name: 'Creative',  members: 3, jobs: 624 },
      { name: 'Founder',   members: 1, jobs: 110 }
    ]
  },
  aurora: {
    kpis: { ctr_lift: 34.1, cvr_lift: 28.6, revenue_attr: 262000, rec_share: 44 },
    concepts: [
      { name: 'Client A · Pre-launch', impressions: 620000, ctr: 5.8, cvr: 3.4, rev: 88200 },
      { name: 'Client B · Always-on',  impressions: 540000, ctr: 5.1, cvr: 3.1, rev: 71400 },
      { name: 'Client C · Festive',    impressions: 380000, ctr: 4.6, cvr: 2.9, rev: 52800 }
    ],
    teams: [
      { name: 'Strategy',  members: 4, jobs: 480 },
      { name: 'Production',members: 12, jobs: 3680 },
      { name: 'Media buy', members: 6, jobs: 1820 }
    ]
  }
}

const cur = computed(() => data[tenant.value])
const totalJobs = computed(() => cur.value.teams.reduce((s, t) => s + t.jobs, 0))

const lift7d = computed(() => Array.from({ length: 7 }, (_, i) => Math.round(cur.value.kpis.ctr_lift * (0.8 + i * 0.05))))
</script>

<template>
  <div class="pd">
    <div class="card head">
      <div class="th">
        <div>
          <div class="kicker">Tenant impact dashboard · embeddable</div>
          <h3>How AdForge is moving the needle</h3>
          <p class="meta">Customer-facing analytics. Same widgets are embedded in the tenant's own portal via JWT-scoped SDK.</p>
        </div>
        <div class="tenant-pick">
          <button v-for="t in tenants" :key="t.id" :class="{ on: tenant === t.id }" @click="tenant = t.id" type="button">
            <span class="tp-logo">{{ t.logo }}</span>{{ t.name }}
          </button>
        </div>
      </div>
    </div>

    <div class="kpi-row">
      <div class="card kpi">
        <div class="kk">CTR lift · AI vs control</div>
        <div class="kv grad-text">+{{ cur.kpis.ctr_lift }}%</div>
        <div class="kd up">▲ trending up · 7d</div>
      </div>
      <div class="card kpi">
        <div class="kk">CVR lift · AI vs control</div>
        <div class="kv grad-text">+{{ cur.kpis.cvr_lift }}%</div>
        <div class="kd up">▲ statistically significant</div>
      </div>
      <div class="card kpi">
        <div class="kk">Revenue attributed</div>
        <div class="kv">${{ cur.kpis.revenue_attr.toLocaleString() }}</div>
        <div class="kd dimc">last 30 days</div>
      </div>
      <div class="card kpi">
        <div class="kk">Share of conversions</div>
        <div class="kv">{{ cur.kpis.rec_share }}%</div>
        <div class="kd dimc">from AI-recommended creatives</div>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>Top performing concepts</h3>
        <p class="meta">Ranked by attributed revenue.</p>
        <table class="cp">
          <thead>
            <tr>
              <th>Concept</th>
              <th class="num">Impressions</th>
              <th class="num">CTR</th>
              <th class="num">CVR</th>
              <th class="num">Revenue</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(c, i) in cur.concepts" :key="c.name">
              <td>
                <span class="rank">#{{ i + 1 }}</span>
                <span class="cn">{{ c.name }}</span>
              </td>
              <td class="num">{{ (c.impressions / 1000).toFixed(0) }}k</td>
              <td class="num"><strong>{{ c.ctr }}%</strong></td>
              <td class="num"><strong>{{ c.cvr }}%</strong></td>
              <td class="num grad-text">${{ c.rev.toLocaleString() }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>Usage by team</h3>
        <p class="meta">{{ totalJobs.toLocaleString() }} render jobs across {{ cur.teams.length }} teams.</p>
        <div class="teams">
          <div v-for="t in cur.teams" :key="t.name" class="te">
            <div class="te-head">
              <span class="te-name">{{ t.name }}</span>
              <span class="te-meta">{{ t.members }} ppl · {{ t.jobs }} jobs</span>
            </div>
            <div class="te-bar">
              <div class="te-fill" :style="{ width: (t.jobs / totalJobs * 100) + '%' }"></div>
            </div>
            <div class="te-pct">{{ Math.round(t.jobs / totalJobs * 100) }}%</div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <h3>CTR lift trend · last 7 days</h3>
      <p class="meta">Holdout group vs treatment. Lift compounds as AI personalizes per cohort.</p>
      <svg viewBox="0 0 380 100" class="trend" preserveAspectRatio="none">
        <g stroke="var(--border)" stroke-dasharray="3 3" stroke-width="1">
          <line x1="0" y1="80" x2="380" y2="80" />
          <line x1="0" y1="40" x2="380" y2="40" />
        </g>
        <path :d="lift7d.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i / 6) * 380},${100 - (v / 50 * 80)}`).join(' ')"
          fill="none" stroke="url(#tg)" stroke-width="2.5" stroke-linecap="round" />
        <g v-for="(v, i) in lift7d" :key="i">
          <circle :cx="(i / 6) * 380" :cy="100 - (v / 50 * 80)" r="4" fill="var(--primary-2)" />
          <text :x="(i / 6) * 380" :y="100 - (v / 50 * 80) - 10" font-size="9" fill="var(--text)" text-anchor="middle">+{{ v }}%</text>
        </g>
        <defs>
          <linearGradient id="tg" x1="0" x2="1">
            <stop offset="0" stop-color="#7c5cff" />
            <stop offset="1" stop-color="#22d3ee" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  </div>
</template>

<style scoped>
.pd { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; }
.th { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.tenant-pick { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; flex-wrap: wrap; }
.tenant-pick button { padding: 6px 12px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 8px; }
.tenant-pick button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }
.tp-logo { width: 18px; height: 18px; border-radius: 50%; background: rgba(255,255,255,.15); display: grid; place-items: center; font-weight: 800; font-size: 10px; }
.tenant-pick button:not(.on) .tp-logo { background: var(--surface-2); }

.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi { padding: 16px 18px; }
.kk { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }
.kv { font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.kd { font-size: 11px; margin-top: 6px; }
.kd.up { color: var(--success); }
.kd.dimc { color: var(--text-dim); }

.row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.cp { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }
.cp th { text-align: left; padding: 8px 10px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.cp th.num { text-align: right; }
.cp td { padding: 12px 10px; border-bottom: 1px dashed var(--border); }
.cp td.num { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }
.rank { display: inline-block; width: 28px; color: var(--primary-2); font-weight: 800; font-size: 12px; }
.cn { font-weight: 500; }

.teams { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.te { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.te-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.te-name { font-weight: 600; font-size: 13px; }
.te-meta { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.te-bar { height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-bottom: 4px; }
.te-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.te-pct { text-align: right; font-weight: 800; font-variant-numeric: tabular-nums; font-size: 12px; }

.trend { width: 100%; height: 130px; margin-top: 12px; }

@media (max-width: 1024px) {
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
  .row { grid-template-columns: 1fr; }
}
</style>
