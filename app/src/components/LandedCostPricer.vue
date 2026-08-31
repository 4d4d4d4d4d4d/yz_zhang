<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { landedCost, priceForMargin, applyCharm } from '../logic/landedCost.js'

const { t, locale } = useI18n()

// Per-market duty/VAT/processing reality. Charm convention follows what the
// local shelf actually looks like, not a global .99 assumption.
const MARKETS = [
  { code: 'JP', flag: '🇯🇵', cur: 'JPY', fx: 152, dutyPct: 0, vatPct: 10, feePct: 3.6, charm: 'end90' },
  { code: 'DE', flag: '🇩🇪', cur: 'EUR', fx: 0.92, dutyPct: 4.7, vatPct: 19, feePct: 2.4, charm: 'end99' },
  { code: 'BR', flag: '🇧🇷', cur: 'BRL', fx: 5.4, dutyPct: 16, vatPct: 17, feePct: 4.9, charm: 'end99' },
  { code: 'AE', flag: '🇦🇪', cur: 'AED', fx: 3.67, dutyPct: 5, vatPct: 5, feePct: 2.9, charm: 'whole' },
  { code: 'ID', flag: '🇮🇩', cur: 'IDR', fx: 15800, dutyPct: 10, vatPct: 11, feePct: 3.2, charm: 'end900' },
  { code: 'MX', flag: '🇲🇽', cur: 'MXN', fx: 17.2, dutyPct: 7, vatPct: 16, feePct: 3.4, charm: 'end99' }
]

const unit = ref({ fob: 62, freight: 9, insurance: 2, brokeragePct: 1.2, otherFixed: 4 })
const targetMargin = ref(58)
const useCharm = ref(true)

const rows = computed(() => MARKETS.map(m => {
  const cost = landedCost({ ...unit.value, dutyPct: m.dutyPct })
  const raw = priceForMargin({
    landed: cost.total, targetMarginPct: targetMargin.value, vatPct: m.vatPct, paymentFeePct: m.feePct
  })
  const quote = raw && useCharm.value
    ? applyCharm(raw, m.charm, { vatPct: m.vatPct, paymentFeePct: m.feePct, fx: m.fx })
    : raw
  // The charmed price is authoritative in local currency; converting the
  // USD figure back would re-introduce the rounding error it just removed.
  return { ...m, cost, quote, local: quote ? (quote.localGross ?? quote.gross * m.fx) : null }
}))

const unreachable = computed(() => rows.value.filter(r => !r.quote))
const worst = computed(() =>
  rows.value.filter(r => r.quote).reduce((w, r) => (!w || r.cost.borderPct > w.cost.borderPct ? r : w), null))

const usd = n => new Intl.NumberFormat(locale.value, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n)
const localFmt = (n, cur) => new Intl.NumberFormat(locale.value, {
  style: 'currency', currency: cur, maximumFractionDigits: ['JPY', 'IDR'].includes(cur) ? 0 : 2
}).format(n)
</script>

<template>
  <div class="lcp">
    <div class="card head">
      <div>
        <div class="kicker">{{ t('landed.kicker') }}</div>
        <h3>{{ t('landed.title') }}</h3>
        <p class="meta">{{ t('landed.sub') }}</p>
      </div>
      <div class="tot" v-if="worst">
        <div class="tn grad-text">{{ worst.cost.borderPct.toFixed(0) }}%</div>
        <div class="tl">{{ t('landed.worstBorder', { market: t(`market.${worst.code}`) }) }}</div>
      </div>
    </div>

    <div class="card inputs">
      <h3>{{ t('landed.unit') }}</h3>
      <div class="ins">
        <label class="in"><span>{{ t('landed.fob') }}</span>
          <input type="number" min="0" step="1" v-model.number="unit.fob" :aria-label="t('landed.fob')" /></label>
        <label class="in"><span>{{ t('landed.freight') }}</span>
          <input type="number" min="0" step="1" v-model.number="unit.freight" :aria-label="t('landed.freight')" /></label>
        <label class="in"><span>{{ t('landed.insurance') }}</span>
          <input type="number" min="0" step="1" v-model.number="unit.insurance" :aria-label="t('landed.insurance')" /></label>
        <label class="in"><span>{{ t('landed.brokerage') }}</span>
          <input type="number" min="0" step="0.1" v-model.number="unit.brokeragePct" :aria-label="t('landed.brokerage')" /></label>
        <label class="in"><span>{{ t('landed.otherFixed') }}</span>
          <input type="number" min="0" step="1" v-model.number="unit.otherFixed" :aria-label="t('landed.otherFixed')" /></label>
        <label class="in"><span>{{ t('landed.targetMargin') }}</span>
          <input type="number" min="0" max="100" step="1" v-model.number="targetMargin" :aria-label="t('landed.targetMargin')" /></label>
      </div>
      <label class="charm">
        <input type="checkbox" v-model="useCharm" />
        <span>{{ t('landed.charm') }}</span>
      </label>
      <p class="cif-note">{{ t('landed.cifNote') }}</p>
    </div>

    <div class="card">
      <h3>{{ t('landed.ladder') }}</h3>
      <div class="tbl" role="table" :aria-label="t('landed.ladder')">
        <div class="tr th" role="row">
          <span role="columnheader">{{ t('landed.colMarket') }}</span>
          <span class="n" role="columnheader">{{ t('landed.colDuty') }}</span>
          <span class="n" role="columnheader">{{ t('landed.colLanded') }}</span>
          <span class="n" role="columnheader">{{ t('landed.colExVat') }}</span>
          <span class="n" role="columnheader">{{ t('landed.colGross') }}</span>
          <span class="n" role="columnheader">{{ t('landed.colLocal') }}</span>
          <span class="n" role="columnheader">{{ t('landed.colMargin') }}</span>
        </div>
        <div v-for="r in rows" :key="r.code" class="tr" role="row">
          <span role="cell"><span class="flag" aria-hidden="true">{{ r.flag }}</span> {{ t(`market.${r.code}`) }}</span>
          <span class="n dim" role="cell">{{ r.dutyPct }}% · {{ t('landed.vatShort') }} {{ r.vatPct }}%</span>
          <span class="n" role="cell">{{ usd(r.cost.total) }}</span>
          <template v-if="r.quote">
            <span class="n" role="cell">{{ usd(r.quote.exVat) }}</span>
            <span class="n strong" role="cell">{{ usd(r.quote.gross) }}</span>
            <span class="n loc" role="cell">{{ localFmt(r.local, r.cur) }}</span>
            <span class="n" role="cell">
              <span class="mg" :class="r.quote.marginPct >= targetMargin ? 'ok' : 'warn'">{{ r.quote.marginPct.toFixed(1) }}%</span>
              <span v-if="useCharm && r.quote.marginDelta > 0.05" class="delta">+{{ r.quote.marginDelta.toFixed(1) }}</span>
            </span>
          </template>
          <span v-else class="n unreach" role="cell" style="grid-column: span 4">{{ t('landed.unreachable') }}</span>
        </div>
      </div>
      <p v-if="unreachable.length" class="warnline">
        {{ t('landed.unreachableNote', { list: unreachable.map(r => t(`market.${r.code}`)).join(', '), margin: targetMargin }) }}
      </p>
      <p class="foot">{{ t('landed.vatNote') }}</p>
    </div>
  </div>
</template>

<style scoped>
.lcp { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.tot { text-align: right; }
.tn { font-size: 26px; font-weight: 800; line-height: 1; }
.tl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; max-width: 180px; }

.card { padding: 18px 20px; }
.ins { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin: 12px 0; }
.in { display: flex; flex-direction: column; gap: 5px; font-size: 11px; color: var(--text-dim); }
.in input { background: var(--bg-2); border: 1px solid var(--border); border-radius: 7px; padding: 7px 10px;
  color: var(--text); font-size: 13px; font-variant-numeric: tabular-nums; outline: none; width: 100%; }
.in input:focus { border-color: var(--primary); }
.charm { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-dim); cursor: pointer; }
.charm input { accent-color: var(--primary); }
.cif-note, .foot { font-size: 11px; color: var(--text-dim); margin: 12px 0 0; line-height: 1.55; }

.tbl { display: flex; flex-direction: column; margin-top: 12px; overflow-x: auto; }
.tr { display: grid; grid-template-columns: 1.5fr 1.1fr .9fr .9fr .9fr 1.1fr .9fr; gap: 10px; align-items: center;
  padding: 9px 6px; border-bottom: 1px dashed var(--border); font-size: 12px; min-width: 660px; }
.tr.th { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--text-dim);
  font-weight: 700; border-bottom: 1px solid var(--border); }
.n { text-align: right; font-variant-numeric: tabular-nums; }
.dim { color: var(--text-dim); font-size: 11px; }
.strong { font-weight: 700; }
.loc { color: var(--primary-2); }
.flag { font-size: 14px; }
.mg { padding: 1px 6px; border-radius: 4px; font-weight: 800; font-size: 11px; }
.mg.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.mg.warn { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.delta { font-size: 10px; color: #6ee7b7; margin-left: 5px; }
.unreach { color: var(--danger); font-size: 11px; text-align: right; }
.warnline { font-size: 12px; color: #fcd34d; margin: 12px 0 0; }

@media (max-width: 1024px) { .ins { grid-template-columns: repeat(2, 1fr); } }
</style>
