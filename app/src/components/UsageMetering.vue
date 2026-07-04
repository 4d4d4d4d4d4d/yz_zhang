<script setup>
import { ref, computed } from 'vue'

const tenants = [
  { id: 'lumi',     name: 'Lumi DTC',           plan: 'Enterprise', mrr: 9800 },
  { id: 'kaito',    name: 'Kaito Beauty',       plan: 'Growth',     mrr: 2400 },
  { id: 'aurora',   name: 'Aurora Media',       plan: 'Enterprise', mrr: 6200 },
  { id: 'verda',    name: 'Verda Commerce',     plan: 'Starter',    mrr: 0    }
]
const tenant = ref('lumi')
const cur = computed(() => tenants.find(t => t.id === tenant.value))

const meters = {
  lumi: [
    { k: 'API calls',    used: 2840000, included: 3000000, unit: 'req',  rate: '$0.0008 / 1K', cost: 2272 },
    { k: 'GPU seconds',  used: 184000, included: 200000,  unit: 's',    rate: '$0.024 / s',    cost: 4416 },
    { k: 'Renders',      used: 12480, included: 10000,    unit: 'job',  rate: '$0.18 / job',   cost: 2246 },
    { k: 'Storage',      used: 4.2,   included: 5,        unit: 'TB',   rate: '$28 / TB-mo',   cost: 118 }
  ],
  kaito: [
    { k: 'API calls',    used: 460000, included: 500000,  unit: 'req',  rate: '$0.0012 / 1K', cost: 552 },
    { k: 'GPU seconds',  used: 38000, included: 40000,    unit: 's',    rate: '$0.026 / s',    cost: 988 },
    { k: 'Renders',      used: 1840,  included: 2000,     unit: 'job',  rate: '$0.22 / job',   cost: 405 },
    { k: 'Storage',      used: 0.8,   included: 1,        unit: 'TB',   rate: '$32 / TB-mo',   cost: 26 }
  ],
  aurora: [
    { k: 'API calls',    used: 1680000, included: 2000000,unit: 'req',  rate: '$0.0009 / 1K', cost: 1512 },
    { k: 'GPU seconds',  used: 128000,  included: 150000, unit: 's',    rate: '$0.025 / s',    cost: 3200 },
    { k: 'Renders',      used: 7820,    included: 8000,   unit: 'job',  rate: '$0.20 / job',   cost: 1564 },
    { k: 'Storage',      used: 2.4,     included: 3,      unit: 'TB',   rate: '$30 / TB-mo',   cost: 72 }
  ],
  verda: [
    { k: 'API calls',    used: 28000,  included: 50000,   unit: 'req',  rate: '$0.0015 / 1K', cost: 42 },
    { k: 'GPU seconds',  used: 1800,   included: 2000,    unit: 's',    rate: '$0.030 / s',    cost: 54 },
    { k: 'Renders',      used: 142,    included: 200,     unit: 'job',  rate: '$0.25 / job',   cost: 36 },
    { k: 'Storage',      used: 0.04,   included: 0.1,     unit: 'TB',   rate: '$40 / TB-mo',   cost: 2 }
  ]
}

const curMeters = computed(() => meters[tenant.value])
const baseFee = computed(() => ({ Enterprise: 5000, Growth: 999, Starter: 0 }[cur.value.plan]))
const usageCost = computed(() => curMeters.value.reduce((s, m) => s + m.cost, 0))
const overageCost = computed(() => curMeters.value.reduce((s, m) => {
  if (m.used <= m.included) return s
  const ratio = (m.used - m.included) / m.included
  return s + Math.round(m.cost * ratio * 0.4)
}, 0))
const total = computed(() => baseFee.value + usageCost.value)
const dayOfMonth = 22, daysInMonth = 30

const trend = computed(() => {
  const days = 14
  return Array.from({ length: days }, (_, i) => Math.round(total.value / daysInMonth * (0.6 + i * 0.04 + Math.sin(i) * 0.08)))
})
const trendMax = computed(() => Math.max(...trend.value))
</script>

<template>
  <div class="um">
    <div class="card head">
      <div>
        <div class="kicker">Metered billing · Stripe-style</div>
        <h3>Usage &amp; invoice</h3>
        <p class="meta">Real-time meter aggregation. Overages charged at 1.4× rate, invoiced on the 1st of next month.</p>
      </div>
      <div class="tenant-pick">
        <button v-for="t in tenants" :key="t.id" :class="{ on: tenant === t.id }" @click="tenant = t.id" type="button">
          {{ t.name }}<span class="tp-plan">{{ t.plan }}</span>
        </button>
      </div>
    </div>

    <div class="card invoice">
      <div class="inv-grid">
        <div>
          <div class="kicker">{{ cur.name }} · {{ cur.plan }} plan</div>
          <h3>Current invoice · day {{ dayOfMonth }} of {{ daysInMonth }}</h3>
          <p class="meta">Forecast end-of-cycle: <strong>${{ Math.round(total / dayOfMonth * daysInMonth).toLocaleString() }}</strong></p>
        </div>
        <div class="inv-amt">
          <div class="ia-num grad-text">${{ total.toLocaleString() }}</div>
          <div class="ia-lbl">accrued so far</div>
        </div>
      </div>

      <div class="line-items">
        <div class="li">
          <span class="li-name">Platform fee · {{ cur.plan }}</span>
          <span class="li-val">${{ baseFee.toLocaleString() }}</span>
        </div>
        <div v-for="m in curMeters" :key="m.k" class="li">
          <span class="li-name">{{ m.k }} <span class="dimc-i">· {{ m.rate }}</span></span>
          <span class="li-val">${{ m.cost.toLocaleString() }}</span>
        </div>
        <div class="li li-sub">
          <span class="li-name">Subtotal</span>
          <span class="li-val">${{ (baseFee + usageCost).toLocaleString() }}</span>
        </div>
        <div class="li li-warn" v-if="overageCost > 0">
          <span class="li-name">Overage · projected at month-end</span>
          <span class="li-val">+${{ overageCost.toLocaleString() }}</span>
        </div>
      </div>
    </div>

    <div class="card">
      <h3>Meters · {{ dayOfMonth }}/{{ daysInMonth }} of current cycle</h3>
      <div class="meters">
        <div v-for="m in curMeters" :key="m.k" class="m" :class="{ over: m.used > m.included }">
          <div class="m-head">
            <span class="m-name">{{ m.k }}</span>
            <span class="m-rate dimc-i">{{ m.rate }}</span>
          </div>
          <div class="m-bar">
            <div class="m-included" :style="{ width: Math.min(100, m.used / m.included * 100) + '%' }"></div>
            <div v-if="m.used > m.included" class="m-over" :style="{ width: Math.min(40, (m.used - m.included) / m.included * 100) + '%' }"></div>
            <div class="m-line" :style="{ left: Math.min(100, (dayOfMonth / daysInMonth) * 100) + '%' }" title="Pro-rata expected"></div>
          </div>
          <div class="m-foot">
            <span><strong>{{ m.used.toLocaleString() }}</strong> {{ m.unit }} used</span>
            <span class="dimc-i">/ {{ m.included.toLocaleString() }} included</span>
            <span class="m-cost">${{ m.cost.toLocaleString() }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>Cost trend · last 14d</h3>
        <div class="trend">
          <div v-for="(v, i) in trend" :key="i" class="t-col">
            <div class="t-fill" :style="{ height: (v / trendMax * 100) + '%' }"></div>
          </div>
        </div>
        <div class="t-foot">
          <span>${{ trend[0] }} → ${{ trend[trend.length - 1] }}</span>
          <span class="up">+{{ Math.round((trend[trend.length-1] - trend[0]) / trend[0] * 100) }}%</span>
        </div>
      </div>

      <div class="card">
        <h3>Optimization opportunities</h3>
        <div class="opt">
          <div class="op">
            <span class="op-tag save">SAVE</span>
            <div><strong>Cache hit on Vision Agent</strong> · raising threshold from 86% → 94% would cut GPU seconds by ~12% (≈ <strong>${{ Math.round(curMeters[1].cost * 0.12).toLocaleString() }}/mo</strong>)</div>
          </div>
          <div class="op">
            <span class="op-tag tier">UPGRADE</span>
            <div><strong>Renders</strong> · projected {{ Math.round(curMeters[2].used / dayOfMonth * daysInMonth).toLocaleString() }} jobs. Upgrade to Scale tier saves ~$420/mo vs overage.</div>
          </div>
          <div class="op">
            <span class="op-tag commit">COMMIT</span>
            <div>1-year commit on API calls · <strong>save 22%</strong> on this line item. Eligible based on 90-day trend.</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.um { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.dimc-i { color: var(--text-dim); font-size: 11px; }

.tenant-pick { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; flex-wrap: wrap; max-width: 100%; }
.tenant-pick button { padding: 6px 12px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }
.tenant-pick button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }
.tp-plan { font-size: 9px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,.15); }

.invoice { padding: 20px; }
.inv-grid { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 14px; flex-wrap: wrap; }
.inv-amt { text-align: right; }
.ia-num { font-size: 38px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.ia-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.line-items { padding-top: 14px; border-top: 1px solid var(--border); display: flex; flex-direction: column; }
.li { display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }
.li-name { color: var(--text); }
.li-val { font-variant-numeric: tabular-nums; font-weight: 600; }
.li-sub { padding-top: 12px; margin-top: 4px; border-top: 1px solid var(--border); border-bottom: 0; font-weight: 700; }
.li-warn { color: #fcd34d; }
.li-warn .li-val { color: #fcd34d; }

.meters { display: flex; flex-direction: column; gap: 12px; margin-top: 14px; }
.m { padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.m.over { border-color: rgba(251, 191, 36, .4); background: rgba(251, 191, 36, .04); }
.m-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.m-name { font-weight: 600; font-size: 13px; }
.m-bar { position: relative; height: 8px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-bottom: 6px; }
.m-included { position: absolute; left: 0; top: 0; height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); border-radius: 999px; }
.m-over { position: absolute; left: 100%; top: 0; height: 100%; background: #fcd34d; border-radius: 0 999px 999px 0; transform: translateX(-100%); }
.m.over .m-included { background: linear-gradient(90deg, var(--primary), #fcd34d); }
.m.over .m-over { transform: translateX(0); }
.m-line { position: absolute; top: -2px; bottom: -2px; width: 1.5px; background: var(--text); opacity: .5; }
.m-foot { display: flex; gap: 8px; align-items: center; font-size: 12px; }
.m-foot strong { font-variant-numeric: tabular-nums; }
.m-cost { margin-left: auto; font-weight: 800; font-variant-numeric: tabular-nums; }

.row { display: grid; grid-template-columns: 1fr 1.4fr; gap: 16px; }
.trend { display: grid; grid-template-columns: repeat(14, 1fr); gap: 6px; height: 100px; align-items: end; margin-top: 12px; }
.t-col { display: flex; align-items: end; height: 100%; }
.t-fill { width: 100%; background: linear-gradient(180deg, var(--primary), var(--primary-2)); border-radius: 4px 4px 0 0; min-height: 4px; }
.t-foot { display: flex; justify-content: space-between; font-size: 12px; margin-top: 10px; color: var(--text-dim); }
.t-foot .up { color: var(--success); font-weight: 700; }

.opt { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.op { display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); font-size: 13px; line-height: 1.5; }
.op-tag { font-size: 9px; padding: 3px 8px; border-radius: 4px; font-weight: 800; letter-spacing: .05em; flex-shrink: 0; }
.op-tag.save { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.op-tag.tier { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.op-tag.commit { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.op strong { color: var(--text); }

@media (max-width: 1024px) {
  .row { grid-template-columns: 1fr; }
}
</style>
