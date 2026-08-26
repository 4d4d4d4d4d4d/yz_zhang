<script setup>
import { ref, computed } from 'vue'
import { priceQuote, approvalFor } from '../logic/cpq.js'
import { crossBorderQuote } from '../logic/quote.js'
import { CURRENCIES } from '../logic/currency.js'

const catalog = [
  { id: 'platform-ent', name: 'Platform · Enterprise', kind: 'subscription', list: 5000, cost: 1100, unit: 'mo' },
  { id: 'platform-scale',name: 'Platform · Scale',     kind: 'subscription', list: 1800, cost: 480,  unit: 'mo' },
  { id: 'api-tier-1',   name: 'API quota · 3M req',    kind: 'subscription', list: 1200, cost: 240,  unit: 'mo' },
  { id: 'gpu-200k',     name: 'GPU bundle · 200k s',   kind: 'subscription', list: 4800, cost: 1280, unit: 'mo' },
  { id: 'seat',         name: 'User seat',             kind: 'subscription', list:   60, cost:   8,  unit: 'mo' },
  { id: 'onboarding',   name: 'White-glove onboarding',kind: 'one-time',     list: 18000, cost: 6000, unit: 'one' },
  { id: 'training',     name: 'Team training · 2 days', kind: 'one-time',    list:  8000, cost: 2200, unit: 'one' }
]

const lines = ref([
  { sku: 'platform-ent', qty: 12,  discount: 0 },
  { sku: 'gpu-200k',     qty: 12,  discount: 10 },
  { sku: 'api-tier-1',   qty: 12,  discount: 0 },
  { sku: 'seat',         qty: 240, discount: 5 },
  { sku: 'onboarding',   qty: 1,   discount: 0 }
])

const customer = ref({ name: 'Lumen Studios K.K.', term: 12, currency: 'JPY' })

// Spec-15 CPQ engine
const quote = computed(() => priceQuote(lines.value, catalog))
const enriched = computed(() => quote.value.lines)
const total = computed(() => quote.value.totals.net)
const totalDisc = computed(() => quote.value.totals.discount)
const totalGross = computed(() => quote.value.totals.gross)
const blendedMargin = computed(() => quote.value.totals.blendedMargin)
const blendedDisc = computed(() => quote.value.totals.blendedDiscount)

function addLine() { lines.value.push({ sku: 'seat', qty: 1, discount: 0 }) }
function removeLine(i) { lines.value.splice(i, 1) }

const approvalLevel = computed(() => approvalFor(blendedDisc.value))
const marginAlert = computed(() => blendedMargin.value < 50)

// Spec 44 — show the TCV in the buyer's currency (Lumen K.K. is a JP entity).
// Billed in USD; partner currency is a reference at the pegged rate.
const CURRENCY_CODES = Object.keys(CURRENCIES)
const partnerQuote = computed(() => crossBorderQuote(total.value, {
  code: customer.value.currency,
  rate: CURRENCIES[customer.value.currency]?.rate ?? 1
}))
const partnerTotalFmt = computed(() => new Intl.NumberFormat('en', {
  style: 'currency', currency: partnerQuote.value.code, maximumFractionDigits: 0
}).format(partnerQuote.value.net))
</script>

<template>
  <div class="cpq">
    <div class="card head">
      <div>
        <div class="kicker">CPQ · configure → price → quote</div>
        <h3>Quote · {{ customer.name }}</h3>
        <p class="meta">{{ customer.term }}-mo term · discount &amp; margin checked against guardrails on every keystroke.</p>
        <label class="cur-pick">Buyer currency
          <select v-model="customer.currency">
            <option v-for="c in CURRENCY_CODES" :key="c" :value="c">{{ c }}</option>
          </select>
        </label>
      </div>
      <div class="totals">
        <div>
          <div class="tn grad-text">${{ Math.round(total).toLocaleString() }}</div>
          <div class="tl">TCV (net)</div>
          <div v-if="!partnerQuote.isUsd" class="tcv-fx">≈ {{ partnerTotalFmt }} · 1 USD = {{ partnerQuote.rate }} {{ partnerQuote.code }} · billed in USD</div>
        </div>
        <div><div class="tn" :class="marginAlert ? 'risk' : ''">{{ blendedMargin.toFixed(1) }}%</div><div class="tl">Margin</div></div>
        <div><div class="tn">{{ blendedDisc.toFixed(1) }}%</div><div class="tl">Blended discount</div></div>
      </div>
    </div>

    <div class="card">
      <div class="th-row">
        <h3>Line items</h3>
        <button class="btn btn-ghost sm" @click="addLine" type="button">+ Add item</button>
      </div>
      <div class="lines">
        <div class="lh">
          <span>Product</span>
          <span class="num">Qty</span>
          <span class="num">List</span>
          <span class="num">Discount</span>
          <span class="num">Net</span>
          <span class="num">Margin</span>
          <span></span>
        </div>
        <div v-for="(l, i) in enriched" :key="i" class="ln">
          <select v-model="l.sku" @change="lines[i].sku = l.sku">
            <option v-for="p in catalog" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
          <input class="num" type="number" min="1" v-model.number="lines[i].qty" :aria-label="`${l.product.name} quantity`" />
          <span class="num dimc">${{ l.product.list.toLocaleString() }}</span>
          <input class="num" type="number" min="0" max="60" v-model.number="lines[i].discount" :aria-label="`${l.product.name} discount percent`" />
          <span class="num strong">${{ Math.round(l.net).toLocaleString() }}</span>
          <span class="num"><span class="mg-pill" :class="l.margin >= 60 ? 'ok' : l.margin >= 40 ? 'warn' : 'risk'">{{ l.margin.toFixed(0) }}%</span></span>
          <button class="x" @click="removeLine(i)" type="button" title="Remove">×</button>
        </div>
      </div>

      <div class="totals-line">
        <span>Total</span>
        <span class="dimc-i">Gross ${{ Math.round(totalGross).toLocaleString() }} − Discount ${{ Math.round(totalDisc).toLocaleString() }}</span>
        <span class="t-num">${{ Math.round(total).toLocaleString() }}</span>
      </div>
    </div>

    <div class="row">
      <div class="card approval">
        <div class="kicker">Approval routing</div>
        <h3>{{ approvalLevel.level }}</h3>
        <p class="meta">Triggered by blended discount of {{ blendedDisc.toFixed(1) }}%</p>
        <div class="ap-bar">
          <div class="ap-zone" data-z="0–5%">Auto</div>
          <div class="ap-zone" data-z="5–15%">Manager</div>
          <div class="ap-zone" data-z="15–25%">VP</div>
          <div class="ap-zone" data-z="25%+">Exec</div>
          <div class="ap-marker" :style="{ left: Math.min(95, blendedDisc * 3) + '%' }"></div>
        </div>
        <div class="ap-who" :class="approvalLevel.color">
          Next approver · <strong>{{ approvalLevel.who }}</strong>
        </div>
        <div v-if="marginAlert" class="ap-alert">
          <span class="ai-tag">AI</span>
          Margin below floor (50%). Consider trimming GPU bundle discount to 4% to restore margin to 52%.
        </div>
      </div>

      <div class="card">
        <h3>Quote preview</h3>
        <p class="meta">PDF rendered server-side at e-sign time. Customer sees Net + payment schedule.</p>
        <div class="prev">
          <div class="pr-row"><span>Customer</span><strong>{{ customer.name }}</strong></div>
          <div class="pr-row"><span>Term</span><strong>{{ customer.term }} months</strong></div>
          <div class="pr-row"><span>Currency</span><strong>{{ customer.currency }}</strong></div>
          <div class="pr-row"><span>Line items</span><strong>{{ enriched.length }}</strong></div>
          <div class="pr-row"><span>Annual recurring</span><strong>${{ Math.round(enriched.filter(l => l.product.kind === 'subscription').reduce((s, l) => s + l.net, 0)).toLocaleString() }}</strong></div>
          <div class="pr-row"><span>One-time fees</span><strong>${{ Math.round(enriched.filter(l => l.product.kind === 'one-time').reduce((s, l) => s + l.net, 0)).toLocaleString() }}</strong></div>
          <div class="pr-row total"><span>Total contract value</span><strong>${{ Math.round(total).toLocaleString() }}</strong></div>
        </div>
        <div class="pr-actions">
          <button class="btn btn-primary sm" type="button">Send for signature →</button>
          <button class="btn btn-ghost sm" type="button">Save draft</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cpq { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.dimc-i { color: var(--text-dim); font-size: 11px; }

.totals { display: flex; gap: 20px; }
.tn { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.tn.risk { color: var(--danger); }
.tl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }
.tcv-fx { font-size: 11px; color: var(--primary-2); margin-top: 5px; font-variant-numeric: tabular-nums; }
.cur-pick { display: inline-flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 12px; color: var(--text-dim); }
.cur-pick select { background: var(--surface); border: 1px solid var(--border); color: var(--text); border-radius: 8px; padding: 6px 10px; font-size: 13px; }
.cur-pick select:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

.th-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.lines { display: flex; flex-direction: column; gap: 4px; }
.lh, .ln { display: grid; grid-template-columns: 2.4fr 0.6fr 0.8fr 0.8fr 0.9fr 0.6fr 26px; gap: 10px; align-items: center; padding: 8px 10px; }
.lh { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; font-weight: 700; border-bottom: 1px solid var(--border); }
.lh .num, .ln .num { text-align: right; }
.ln { border-bottom: 1px dashed var(--border); font-size: 12px; }
.ln select, .ln input { background: var(--bg-2); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; color: var(--text); font-size: 12px; outline: none; }
.ln select:focus, .ln input:focus { border-color: var(--primary); }
.ln input.num { text-align: right; font-variant-numeric: tabular-nums; }
.strong { font-weight: 700; }
.dimc { color: var(--text-dim); }
.mg-pill { padding: 1px 7px; border-radius: 4px; font-weight: 800; font-size: 11px; }
.mg-pill.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.mg-pill.warn { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.mg-pill.risk { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.x { background: transparent; border: 1px solid var(--border); color: var(--text-dim); border-radius: 6px; width: 26px; height: 26px; cursor: pointer; font-size: 14px; }
.x:hover { color: var(--danger); border-color: var(--danger); }

.totals-line { display: grid; grid-template-columns: auto 1fr auto; gap: 14px; align-items: baseline; padding: 14px 10px 0; margin-top: 10px; border-top: 1px solid var(--border); font-size: 13px; }
.t-num { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; }

.row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.approval { padding: 20px; }
.ap-bar { position: relative; display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 4px; height: 38px; margin: 14px 0; }
.ap-zone { display: grid; place-items: center; border-radius: 6px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; position: relative; }
.ap-zone:nth-child(1) { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.ap-zone:nth-child(2) { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.ap-zone:nth-child(3) { background: rgba(255, 122, 217, .15); color: #f5d0fe; }
.ap-zone:nth-child(4) { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.ap-zone::after { content: attr(data-z); position: absolute; bottom: -16px; left: 50%; transform: translateX(-50%); font-size: 9px; font-weight: 500; color: var(--text-dim); letter-spacing: 0; text-transform: none; }
.ap-marker { position: absolute; top: -6px; bottom: -6px; width: 3px; background: var(--text); border-radius: 2px; box-shadow: 0 0 0 2px rgba(255,255,255,.4); }
.ap-who { margin-top: 30px; font-size: 13px; }
.ap-who strong { color: var(--text); }
.ap-who.ok { color: var(--success); }
.ap-who.warn { color: #fcd34d; }
.ap-who.risk { color: #fca5a5; }
.ap-alert { display: flex; gap: 10px; align-items: flex-start; padding: 12px; background: rgba(248, 113, 113, .08); border: 1px solid rgba(248, 113, 113, .25); border-radius: 10px; font-size: 12px; color: var(--text-dim); margin-top: 14px; line-height: 1.5; }
.ai-tag { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 800; letter-spacing: .05em; flex-shrink: 0; }

.prev { padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); margin-top: 12px; }
.pr-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }
.pr-row:last-of-type { border-bottom: 0; padding-top: 12px; margin-top: 4px; border-top: 1px solid var(--border); font-weight: 700; }
.pr-row.total strong { font-size: 16px; }
.pr-row span { color: var(--text-dim); }
.pr-actions { display: flex; gap: 8px; margin-top: 14px; }

@media (max-width: 1024px) {
  .row { grid-template-columns: 1fr; }
  .lh, .ln { grid-template-columns: 1.6fr 0.5fr 0.7fr 0.7fr 0.9fr 0.6fr 24px; font-size: 11px; }
}
</style>
