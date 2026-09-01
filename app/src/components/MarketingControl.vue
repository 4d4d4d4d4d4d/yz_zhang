<script setup>
import { ref, computed } from 'vue'
import { channelRollup, allocateBudget, pacingStatus, percentShares } from '../logic/marketing.js'
import { proportionZTest, recommendation } from '../logic/significance.js'
import { sortRows, nextDir } from '../logic/sortRows.js'
import { useFormat } from '../composables/useFormat.js'

const { money } = useFormat()

const campaigns = ref([
  { id: 'c1', name: 'Lumi · JP launch', channel: 'TikTok', status: 'live',   spend: 18400, roas: 4.2, ctr: 4.8, cvr: 3.2, delta: 12 },
  { id: 'c2', name: 'Lumi · US holiday', channel: 'Meta',  status: 'live',   spend: 22800, roas: 3.6, ctr: 3.4, cvr: 2.8, delta: 4 },
  { id: 'c3', name: 'Sneaker · Style swap',  channel: 'TikTok', status: 'live',   spend: 14200, roas: 3.8, ctr: 5.0, cvr: 2.4, delta: 18 },
  { id: 'c4', name: 'SaaS · 12s demo',       channel: 'Google', status: 'paused', spend: 6400,  roas: 1.9, ctr: 2.2, cvr: 2.8, delta: -8 },
  { id: 'c5', name: 'Apparel · Lookbook EU', channel: 'Meta',   status: 'live',   spend: 9800,  roas: 3.2, ctr: 4.0, cvr: 2.9, delta: 6 },
  { id: 'c6', name: 'Food · Recipe SEA',     channel: 'YouTube',status: 'draft',  spend: 0,     roas: 0,   ctr: 0,   cvr: 0,   delta: 0 },
  { id: 'c7', name: 'Gadget · BR test',      channel: 'TikTok', status: 'live',   spend: 5600,  roas: 2.1, ctr: 3.6, cvr: 1.9, delta: -14 }
])

const sortKey = ref('spend')
const sortDir = ref('desc')
const filter = ref('all')
const filters = ['all', 'live', 'paused', 'draft']

// Spec 51 — the hand-rolled comparator returned ±dir for equal values and
// never 0, so compare(a,b) === compare(b,a) — an inconsistent comparator with
// implementation-defined ordering. sortRows is stable and type-aware.
const sorted = computed(() =>
  sortRows(
    campaigns.value.filter(c => filter.value === 'all' || c.status === filter.value),
    sortKey.value,
    sortDir.value
  )
)

function sortBy(k) {
  sortDir.value = nextDir(sortKey.value, k, sortDir.value)
  sortKey.value = k
}

function toggleStatus(c) {
  c.status = c.status === 'live' ? 'paused' : 'live'
}
function scale(c, by) {
  c.spend = Math.max(0, Math.round(c.spend * (1 + by)))
}

// Spec 51 — the verdict was a hardcoded `probability: 96.8 / status:
// 'significant'`. It now comes from the spec-45 two-proportion z-test over the
// variants' own visitors and conversions.
const abTest = ref({
  variantA: { name: 'UGC Reel', spend: 8400, visitors: 92400, conv: 268 },
  variantB: { name: 'Studio Hero', spend: 8200, visitors: 91600, conv: 198 }
})
const abResult = computed(() => proportionZTest({
  convA: abTest.value.variantA.conv, nA: abTest.value.variantA.visitors,
  convB: abTest.value.variantB.conv, nB: abTest.value.variantB.visitors
}))
const abVerdict = computed(() => recommendation(abResult.value))
const AB_LABEL = {
  ship: 'Ship B — significant lift',
  rollback: 'Keep A — B is significantly worse',
  keep_testing: 'Keep testing — not yet significant',
  invalid: 'Awaiting traffic'
}

const geo = ref([
  { code: 'JP', name: 'Japan',  value: 92, share: 22 },
  { code: 'US', name: 'United States', value: 88, share: 28 },
  { code: 'KR', name: 'Korea',  value: 84, share: 11 },
  { code: 'BR', name: 'Brazil', value: 78, share: 9  },
  { code: 'DE', name: 'Germany',value: 72, share: 8  },
  { code: 'MX', name: 'Mexico', value: 64, share: 6  },
  { code: 'FR', name: 'France', value: 70, share: 7  },
  { code: 'TH', name: 'Thailand', value: 60, share: 5 },
  { code: 'ID', name: 'Indonesia', value: 58, share: 4 }
])
const activeGeo = ref(null)

const budget = ref({
  Meta: 38, TikTok: 32, Google: 18, YouTube: 12
})

// Spec 51 — the "AI suggestion" was a hardcoded object. It is now the output
// of the ROAS-proportional water-fill allocator running over the campaigns'
// own spend-weighted channel performance, with a 5% floor per channel so no
// live channel is starved outright.
const TOTAL_BUDGET = 100000
const PERIOD_DAYS = 30
const ELAPSED_DAYS = 18

const channels = computed(() => channelRollup(campaigns.value))
const allocation = computed(() => allocateBudget(
  TOTAL_BUDGET,
  channels.value.map(c => ({ id: c.id, roas: c.roas, min: TOTAL_BUDGET * 0.05 }))
))
// Largest-remainder so the shares total exactly 100 — applyAI feeds these
// straight into the reallocator, which assumes they do.
const aiSuggestion = computed(() => percentShares(allocation.value.allocations))

const totalSpent = computed(() => campaigns.value.reduce((s, c) => s + c.spend, 0))
const pacing = computed(() => pacingStatus(TOTAL_BUDGET, totalSpent.value, ELAPSED_DAYS, PERIOD_DAYS))

function reallocate(channel, val) {
  const old = budget.value[channel]
  const diff = val - old
  budget.value[channel] = val
  const others = Object.keys(budget.value).filter(k => k !== channel)
  let totalOther = others.reduce((s, k) => s + budget.value[k], 0)
  if (totalOther === 0) return
  for (const k of others) {
    budget.value[k] = Math.max(0, Math.round(budget.value[k] - diff * (budget.value[k] / totalOther)))
  }
  const sum = Object.values(budget.value).reduce((a, b) => a + b, 0)
  if (sum !== 100) budget.value[others[0]] += 100 - sum
}
function applyAI() { budget.value = { ...aiSuggestion.value } }
</script>

<template>
  <div class="ctrl">
    <div class="card">
      <div class="th-row">
        <h3>Active campaigns</h3>
        <div class="filter">
          <button v-for="f in filters" :key="f" :class="{ on: filter === f }" @click="filter = f" type="button">{{ f }}</button>
        </div>
      </div>
      <table class="t">
        <thead>
          <tr>
            <th>Campaign</th>
            <th>Channel</th>
            <th>Status</th>
            <th class="num sortable" @click="sortBy('spend')">Spend <span class="arr">{{ sortKey === 'spend' ? (sortDir === 'asc' ? '▲' : '▼') : '' }}</span></th>
            <th class="num sortable" @click="sortBy('roas')">ROAS <span class="arr">{{ sortKey === 'roas' ? (sortDir === 'asc' ? '▲' : '▼') : '' }}</span></th>
            <th class="num sortable" @click="sortBy('ctr')">CTR <span class="arr">{{ sortKey === 'ctr' ? (sortDir === 'asc' ? '▲' : '▼') : '' }}</span></th>
            <th class="num sortable" @click="sortBy('cvr')">CVR <span class="arr">{{ sortKey === 'cvr' ? (sortDir === 'asc' ? '▲' : '▼') : '' }}</span></th>
            <th class="num">Δ 7d</th>
            <th class="acts">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in sorted" :key="c.id">
            <td class="cn">{{ c.name }}</td>
            <td><span class="ch" :class="c.channel.toLowerCase()">{{ c.channel }}</span></td>
            <td><span class="st" :class="c.status">{{ c.status }}</span></td>
            <td class="num">${{ c.spend.toLocaleString() }}</td>
            <td class="num">{{ c.roas.toFixed(1) }}×</td>
            <td class="num">{{ c.ctr.toFixed(1) }}%</td>
            <td class="num">{{ c.cvr.toFixed(1) }}%</td>
            <td class="num" :class="c.delta > 0 ? 'up' : c.delta < 0 ? 'down' : ''">
              {{ c.delta > 0 ? '+' : '' }}{{ c.delta }}%
            </td>
            <td class="acts">
              <button class="mini" @click="toggleStatus(c)" type="button" :disabled="c.status === 'draft'">
                {{ c.status === 'live' ? 'Pause' : 'Resume' }}
              </button>
              <button class="mini" @click="scale(c, 0.2)" type="button" :disabled="c.status !== 'live'">+20%</button>
              <button class="mini" @click="scale(c, -0.2)" type="button" :disabled="c.status !== 'live'">−20%</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="grid">
      <div class="card ab">
        <div class="th-row">
          <h3>A/B test · Lumi creative</h3>
          <span class="abs" :class="abResult.significant ? 'significant' : 'collecting'">{{ abResult.significant ? '● significant' : '○ collecting' }}</span>
        </div>
        <div class="ab-grid">
          <div class="variant" :class="{ winner: abTest.variantA.conv > abTest.variantB.conv }">
            <div class="vh">
              <span class="vt">A</span>
              <span class="vn">{{ abTest.variantA.name }}</span>
              <span v-if="abTest.variantA.conv > abTest.variantB.conv" class="badge">🏆 winner</span>
            </div>
            <div class="vkpi">
              <div><div class="vn-num">{{ abTest.variantA.conv }}</div><div class="vn-lbl">Conv</div></div>
              <div><div class="vn-num">{{ ((abTest.variantA.conv / abTest.variantA.visitors) * 100).toFixed(2) }}%</div><div class="vn-lbl">CVR</div></div>
              <div><div class="vn-num">${{ abTest.variantA.spend.toLocaleString() }}</div><div class="vn-lbl">Spend</div></div>
            </div>
          </div>
          <div class="variant" :class="{ winner: abTest.variantB.conv > abTest.variantA.conv }">
            <div class="vh">
              <span class="vt">B</span>
              <span class="vn">{{ abTest.variantB.name }}</span>
            </div>
            <div class="vkpi">
              <div><div class="vn-num">{{ abTest.variantB.conv }}</div><div class="vn-lbl">Conv</div></div>
              <div><div class="vn-num">{{ ((abTest.variantB.conv / abTest.variantB.visitors) * 100).toFixed(2) }}%</div><div class="vn-lbl">CVR</div></div>
              <div><div class="vn-num">${{ abTest.variantB.spend.toLocaleString() }}</div><div class="vn-lbl">Spend</div></div>
            </div>
          </div>
        </div>
        <div class="ab-foot">
          <div>
            <div class="kicker">Confidence (1 − p)</div>
            <div class="big-prob grad-text">{{ abResult.valid ? ((1 - abResult.pValue) * 100).toFixed(1) : '—' }}%</div>
            <div class="kl">p {{ abResult.valid ? (abResult.pValue < 0.001 ? '<0.001' : abResult.pValue.toFixed(3)) : '—' }} · z {{ abResult.valid ? abResult.z.toFixed(2) : '—' }}</div>
          </div>
          <div>
            <div class="kicker">Sample</div>
            <div class="big-prob">{{ (abTest.variantA.visitors + abTest.variantB.visitors).toLocaleString() }}</div>
            <div class="kl" v-if="abResult.valid">
              95% CI [{{ (abResult.ci95[0] * 100).toFixed(2) }}%, {{ (abResult.ci95[1] * 100).toFixed(2) }}%]
            </div>
          </div>
          <button class="btn btn-primary" type="button">{{ AB_LABEL[abVerdict] }}</button>
        </div>
      </div>

      <div class="card geo">
        <div class="th-row">
          <h3>Geo performance</h3>
          <span class="meta">{{ activeGeo ? activeGeo.name : 'click a country to filter' }}</span>
        </div>
        <div class="geo-list">
          <button v-for="g in geo" :key="g.code"
            class="g-row" :class="{ on: activeGeo?.code === g.code }"
            @click="activeGeo = activeGeo?.code === g.code ? null : g" type="button">
            <span class="g-flag">{{ g.code }}</span>
            <span class="g-name">{{ g.name }}</span>
            <div class="g-bar">
              <div class="g-fill" :style="{ width: g.value + '%' }"></div>
            </div>
            <span class="g-val">{{ g.value }}</span>
            <span class="g-share">{{ g.share }}%</span>
          </button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="th-row">
        <h3>Budget reallocator</h3>
        <button class="btn btn-ghost sm" @click="applyAI" type="button">Apply AI suggestion ↺</button>
      </div>
      <p class="re-note">
        Total stays at 100%. The suggestion is a ROAS-proportional water-fill over
        spend-weighted channel performance, floored at 5% per channel.
      </p>

      <div class="pacing" :class="pacing.status">
        <div class="pc-row">
          <div>
            <div class="kicker">Budget pacing · day {{ ELAPSED_DAYS }} of {{ PERIOD_DAYS }}</div>
            <h4>{{ money(totalSpent) }} spent of {{ money(TOTAL_BUDGET) }}</h4>
          </div>
          <div class="pc-status">
            <span class="pc-pill" :class="pacing.status">{{ pacing.status }}</span>
            <div class="pc-delta">{{ pacing.delta >= 0 ? '+' : '−' }}{{ money(Math.abs(pacing.delta)) }} vs target</div>
          </div>
        </div>
        <div class="pc-bar">
          <div class="pc-spent" :style="{ width: Math.min(100, totalSpent / TOTAL_BUDGET * 100) + '%' }"></div>
          <div class="pc-target" :style="{ left: Math.min(100, pacing.target / TOTAL_BUDGET * 100) + '%' }" title="On-pace target"></div>
        </div>
        <div class="pc-foot">
          <span>Run rate {{ money(pacing.dailyRunRate) }}/day</span>
          <span>Projected {{ money(pacing.projectedTotal) }} by day {{ PERIOD_DAYS }}</span>
        </div>
      </div>

      <div class="chan-alloc">
        <div v-for="c in channels" :key="c.id" class="ca">
          <span class="ca-name">{{ c.id }}</span>
          <span class="ca-roas">{{ c.roas.toFixed(2) }}× blended</span>
          <span class="ca-amt">{{ money(allocation.allocations[c.id] ?? 0) }}</span>
        </div>
      </div>
      <div class="reallocator">
        <div v-for="(v, k) in budget" :key="k" class="ch-row">
          <div class="ch-lbl">
            <span class="ch-name" :class="k.toLowerCase()">{{ k }}</span>
            <span class="ch-suggest">AI: {{ aiSuggestion[k] ?? 0 }}%</span>
          </div>
          <input type="range" min="0" max="100" :value="v" @input="reallocate(k, +$event.target.value)" :aria-label="`${k} budget share percent`" />
          <div class="ch-val">{{ v }}%</div>
        </div>
      </div>
      <div class="total">Sum · {{ Object.values(budget).reduce((a, b) => a + b, 0) }}%</div>
    </div>
  </div>
</template>

<style scoped>
.ctrl { display: flex; flex-direction: column; gap: 16px; }
.th-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.meta { color: var(--text-dim); font-size: 12px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.filter { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; }
.filter button { padding: 5px 12px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 12px; text-transform: capitalize; }
.filter button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.t { width: 100%; border-collapse: collapse; font-size: 13px; }
.t th { text-align: left; padding: 10px 12px; font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 600; }
.t th.num { text-align: right; }
.t th.acts { text-align: right; }
.t th.sortable { cursor: pointer; user-select: none; }
.t th.sortable:hover { color: var(--text); }
.arr { display: inline-block; width: 12px; color: var(--primary-2); }
.t td { padding: 12px; border-bottom: 1px dashed var(--border); }
.t td.num { text-align: right; font-variant-numeric: tabular-nums; }
.t td.num.up { color: var(--success); }
.t td.num.down { color: var(--danger); }
.t td.acts { text-align: right; }
.t tr:hover td { background: rgba(124, 92, 255, .04); }
.cn { font-weight: 500; }
.ch { font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.ch.meta { background: rgba(24, 119, 242, .15); color: #93c5fd; }
.ch.tiktok { background: rgba(254, 44, 85, .15); color: #fda4af; }
.ch.google { background: rgba(52, 168, 83, .15); color: #6ee7b7; }
.ch.youtube { background: rgba(255, 0, 0, .15); color: #fecaca; }
.st { font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 700; letter-spacing: .06em; }
.st.live { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.st.paused { background: rgba(255, 255, 255, .08); color: var(--text-dim); }
.st.draft { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.acts .mini { padding: 4px 8px; border-radius: 6px; background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 11px; cursor: pointer; margin-left: 4px; }
.acts .mini:hover:not(:disabled) { border-color: var(--primary); }
.acts .mini:disabled { opacity: .4; cursor: not-allowed; }

.grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }

.ab .abs { font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 999px; }
.ab .abs.significant { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.ab-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 18px; }
.variant { padding: 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.variant.winner { border-color: var(--success); background: rgba(52, 211, 153, .06); }
.vh { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.vt { width: 24px; height: 24px; border-radius: 50%; background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; display: grid; place-items: center; font-weight: 700; font-size: 12px; }
.vn { font-weight: 600; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(52, 211, 153, .2); color: #6ee7b7; margin-left: auto; }
.vkpi { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.vn-num { font-size: 17px; font-weight: 700; font-variant-numeric: tabular-nums; }
.vn-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.ab-foot { display: grid; grid-template-columns: 1fr 1fr auto; gap: 16px; align-items: center; padding-top: 16px; border-top: 1px solid var(--border); }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.big-prob { font-size: 26px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; margin-top: 4px; }
.kl { font-size: 11px; color: var(--text-dim); }

.geo-list { display: flex; flex-direction: column; gap: 6px; }
.g-row { display: grid; grid-template-columns: 40px 1fr 1fr 40px 50px; gap: 12px; align-items: center; padding: 8px 12px; border-radius: 8px; background: transparent; border: 1px solid transparent; color: var(--text); cursor: pointer; text-align: left; font-size: 13px; }
.g-row:hover { background: var(--surface); }
.g-row.on { background: rgba(124, 92, 255, .12); border-color: rgba(124, 92, 255, .35); }
.g-flag { font-weight: 700; color: var(--primary-2); font-size: 11px; }
.g-name { font-size: 13px; }
.g-bar { height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.g-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.g-val { font-variant-numeric: tabular-nums; font-size: 12px; text-align: right; }
.g-share { color: var(--text-dim); font-size: 11px; text-align: right; font-variant-numeric: tabular-nums; }

.re-note { color: var(--text-dim); margin: 0 0 16px; font-size: 13px; }
.reallocator { display: flex; flex-direction: column; gap: 12px; }
.ch-row { display: grid; grid-template-columns: 140px 1fr 50px; gap: 16px; align-items: center; }
.ch-lbl { display: flex; flex-direction: column; gap: 2px; }
.ch-name { font-weight: 600; font-size: 13px; }
.ch-name.meta { color: #93c5fd; }
.ch-name.tiktok { color: #fda4af; }
.ch-name.google { color: #6ee7b7; }
.ch-name.youtube { color: #fecaca; }
.ch-suggest { font-size: 10px; color: var(--text-dim); }
.pacing { margin: 14px 0; padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); border-left-width: 3px; }
.pacing.over { border-left-color: var(--danger); }
.pacing.under { border-left-color: #fbbf24; }
.pacing.on-track { border-left-color: var(--success); }
.pc-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; flex-wrap: wrap; }
.pc-row h4 { margin: 4px 0 0; font-size: 16px; font-variant-numeric: tabular-nums; }
.pc-status { text-align: right; }
.pc-pill { font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; padding: 3px 9px; border-radius: 999px; background: var(--surface-2); }
.pc-pill.over { color: var(--danger); }
.pc-pill.under { color: #fbbf24; }
.pc-pill.on-track { color: var(--success); }
.pc-delta { font-size: 11px; color: var(--text-dim); margin-top: 4px; font-variant-numeric: tabular-nums; }
.pc-bar { position: relative; height: 10px; border-radius: 999px; background: var(--surface-2); margin: 12px 0 6px; overflow: hidden; }
.pc-spent { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.pc-target { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--text); }
.pc-foot { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; flex-wrap: wrap; gap: 8px; }
.chan-alloc { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.ca { display: grid; grid-template-columns: 1fr auto auto; gap: 12px; align-items: baseline; font-size: 12px; padding: 6px 8px; border-radius: 7px; background: var(--surface); }
.ca-name { font-weight: 600; }
.ca-roas { color: var(--text-dim); font-variant-numeric: tabular-nums; }
.ca-amt { font-weight: 700; font-variant-numeric: tabular-nums; min-width: 76px; text-align: right; }
.ch-row input { accent-color: var(--primary); width: 100%; }
.ch-val { font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; }
.total { margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border); font-size: 12px; color: var(--text-dim); text-align: right; }

@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; }
  .t { font-size: 12px; }
  .t th:nth-child(6), .t td:nth-child(6),
  .t th:nth-child(7), .t td:nth-child(7) { display: none; }
}
@media (max-width: 720px) {
  .ch-row { grid-template-columns: 1fr; }
  .ab-grid { grid-template-columns: 1fr; }
  .ab-foot { grid-template-columns: 1fr; }
}
</style>
