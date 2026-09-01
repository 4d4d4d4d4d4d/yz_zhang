<script setup>
import { ref, computed } from 'vue'
import { invoice } from '../logic/metering.js'
import { TENANTS as tenants, METERS as meters, PLAN_BASE_FEES } from '../data/workspace.js'
import { useFormat } from '../composables/useFormat.js'
import { useI18n } from 'vue-i18n'

const { money, num, pct } = useFormat()
const { t } = useI18n()

const tenant = ref('lumi')
const cur = computed(() => tenants.find(t => t.id === tenant.value))


const curMeters = computed(() => meters[tenant.value])
const baseFee = computed(() => PLAN_BASE_FEES[cur.value.plan])
// Spec-15 metering engine — invoice total includes the overage premium
// (R1 correction: the inline version left overage out of the total).
const inv = computed(() => invoice(baseFee.value, curMeters.value))
const usageCost = computed(() => inv.value.usage)
const overageCost = computed(() => inv.value.overage)
const total = computed(() => inv.value.total)
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
        <div class="kicker">{{ t('metering.kicker') }}</div>
        <h3>{{ t('metering.title') }}</h3>
        <p class="meta">{{ t('metering.sub') }}</p>
      </div>
      <div class="tenant-pick">
        <button v-for="tn in tenants" :key="tn.id" :class="{ on: tenant === tn.id }" @click="tenant = tn.id" type="button">
          {{ tn.name }}<span class="tp-plan">{{ tn.plan }}</span>
        </button>
      </div>
    </div>

    <div class="card invoice">
      <div class="inv-grid">
        <div>
          <div class="kicker">{{ t('metering.planLine', { name: cur.name, plan: cur.plan }) }}</div>
          <h3>{{ t('metering.invoiceTitle', { day: dayOfMonth, days: daysInMonth }) }}</h3>
          <p class="meta">{{ t('metering.forecast') }} <strong>{{ money(total / dayOfMonth * daysInMonth) }}</strong></p>
        </div>
        <div class="inv-amt">
          <div class="ia-num grad-text">{{ money(total) }}</div>
          <div class="ia-lbl">{{ t('metering.accrued') }}</div>
        </div>
      </div>

      <div class="line-items">
        <div class="li">
          <span class="li-name">{{ t('metering.platformFee', { plan: cur.plan }) }}</span>
          <span class="li-val">{{ money(baseFee) }}</span>
        </div>
        <div v-for="m in curMeters" :key="m.k" class="li">
          <span class="li-name">{{ m.k }} <span class="dimc-i">· {{ m.rate }}</span></span>
          <span class="li-val">{{ money(m.cost) }}</span>
        </div>
        <div class="li li-sub">
          <span class="li-name">{{ t('metering.subtotal') }}</span>
          <span class="li-val">{{ money(baseFee + usageCost) }}</span>
        </div>
        <div class="li li-warn" v-if="overageCost > 0">
          <span class="li-name">{{ t('metering.overage') }}</span>
          <span class="li-val">+{{ money(overageCost) }}</span>
        </div>
      </div>
    </div>

    <div class="card">
      <h3>{{ t('metering.metersTitle', { day: dayOfMonth, days: daysInMonth }) }}</h3>
      <div class="meters">
        <div v-for="m in curMeters" :key="m.k" class="m" :class="{ over: m.used > m.included }">
          <div class="m-head">
            <span class="m-name">{{ m.k }}</span>
            <span class="m-rate dimc-i">{{ m.rate }}</span>
          </div>
          <div class="m-bar">
            <div class="m-included" :style="{ width: Math.min(100, m.used / m.included * 100) + '%' }"></div>
            <div v-if="m.used > m.included" class="m-over" :style="{ width: Math.min(40, (m.used - m.included) / m.included * 100) + '%' }"></div>
            <div class="m-line" :style="{ left: Math.min(100, (dayOfMonth / daysInMonth) * 100) + '%' }" :title="t('metering.proRata')"></div>
          </div>
          <div class="m-foot">
            <span><strong>{{ num(m.used) }}</strong> {{ m.unit }} {{ t('metering.used') }}</span>
            <span class="dimc-i">/ {{ num(m.included) }} {{ t('metering.included') }}</span>
            <span class="m-cost">{{ money(m.cost) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>{{ t('metering.trendTitle') }}</h3>
        <div class="trend">
          <div v-for="(v, i) in trend" :key="i" class="t-col">
            <div class="t-fill" :style="{ height: (v / trendMax * 100) + '%' }"></div>
          </div>
        </div>
        <div class="t-foot">
          <span>{{ money(trend[0]) }} → {{ money(trend[trend.length - 1]) }}</span>
          <span class="up">+{{ pct((trend[trend.length-1] - trend[0]) / trend[0], { digits: 0 }) }}</span>
        </div>
      </div>

      <div class="card">
        <h3>{{ t('metering.optTitle') }}</h3>
        <div class="opt">
          <div class="op">
            <span class="op-tag save">{{ t('metering.tagSave') }}</span>
            <div><strong>{{ t('metering.optCache') }}</strong> {{ t('metering.optCacheBody', { amount: money(curMeters[1].cost * 0.12) }) }}</div>
          </div>
          <div class="op">
            <span class="op-tag tier">{{ t('metering.tagUpgrade') }}</span>
            <div><strong>{{ t('metering.optRenders') }}</strong> {{ t('metering.optRendersBody', { jobs: num(curMeters[2].used / dayOfMonth * daysInMonth) }) }}</div>
          </div>
          <div class="op">
            <span class="op-tag commit">{{ t('metering.tagCommit') }}</span>
            <div>{{ t('metering.optCommit') }} <strong>{{ t('metering.optCommitSave') }}</strong> {{ t('metering.optCommitBody') }}</div>
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
