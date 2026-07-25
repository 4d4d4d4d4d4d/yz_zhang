<script setup>
import { ref, computed } from 'vue'
import { useSortable } from '../composables/useSortable.js'
import { useFormat } from '../composables/useFormat.js'
import { toCsv } from '../logic/csv.js'

const { money, num } = useFormat()

const orders = ref([
  { id: 'O-20419', partner: 'Lumen Studios',  market: 'JP', placed: 'Dec 02', items: 3, total: 84000, pay: 'paid',    fulfill: 'shipped',  due: '—' },
  { id: 'O-20418', partner: 'Aurora Media',   market: 'SG', placed: 'Dec 01', items: 1, total: 32000, pay: 'invoiced', fulfill: 'preparing',due: 'Dec 18' },
  { id: 'O-20417', partner: 'Northwave',      market: 'BR', placed: 'Nov 28', items: 2, total: 142000,pay: 'paid',    fulfill: 'delivered',due: '—' },
  { id: 'O-20416', partner: 'Kaito Beauty',   market: 'JP', placed: 'Nov 27', items: 4, total: 18400, pay: 'paid',    fulfill: 'shipped',  due: '—' },
  { id: 'O-20415', partner: 'Mizu Logistics', market: 'JP', placed: 'Nov 26', items: 1, total:  9800, pay: 'overdue', fulfill: 'on-hold',  due: 'Dec 03' },
  { id: 'O-20414', partner: 'Helio Network',  market: 'BR', placed: 'Nov 24', items: 1, total:  4200, pay: 'invoiced', fulfill: 'preparing',due: 'Dec 10' },
  { id: 'O-20413', partner: 'Cobalt Legal',   market: 'DE', placed: 'Nov 22', items: 2, total: 16800, pay: 'paid',    fulfill: 'delivered',due: '—' },
  { id: 'O-20412', partner: 'Verda Commerce', market: 'SG', placed: 'Nov 20', items: 1, total:  6400, pay: 'paid',    fulfill: 'delivered',due: '—' }
])

const filterPay = ref('all')
const filterFul = ref('all')
const query = ref('')

const payStates = ['all', 'paid', 'invoiced', 'overdue']
const fulStates = ['all', 'preparing', 'shipped', 'delivered', 'on-hold']

const filtered = computed(() => orders.value.filter(o => {
  if (filterPay.value !== 'all' && o.pay !== filterPay.value) return false
  if (filterFul.value !== 'all' && o.fulfill !== filterFul.value) return false
  if (query.value && !(o.id + o.partner).toLowerCase().includes(query.value.toLowerCase())) return false
  return true
}))

const summary = computed(() => ({
  count: orders.value.length,
  gmv: orders.value.reduce((s, o) => s + o.total, 0),
  outstanding: orders.value.filter(o => o.pay !== 'paid').reduce((s, o) => s + o.total, 0),
  overdue: orders.value.filter(o => o.pay === 'overdue').reduce((s, o) => s + o.total, 0)
}))

// Column model drives both the sortable header and the CSV export.
const COLUMNS = [
  { key: 'id', label: 'Order' },
  { key: 'partner', label: 'Partner' },
  { key: 'market', label: 'Market' },
  { key: 'items', label: 'Items', num: true },
  { key: 'total', label: 'Total', num: true },
  { key: 'pay', label: 'Payment' },
  { key: 'fulfill', label: 'Fulfillment' },
  { key: 'due', label: 'Due' }
]

const { sorted, sortBy, ariaSort, sortKey, sortDir } = useSortable(filtered)

function sortGlyph(key) {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'asc' ? '▲' : '▼'
}

// Export the currently sorted+filtered view — what you see is what you get.
function exportCsv() {
  const csv = toCsv(sorted.value, COLUMNS)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'orders.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="ob">
    <div class="card head">
      <div>
        <div class="kicker">Order book · B2B</div>
        <h3>{{ orders.length }} orders · {{ money(summary.gmv) }} GMV month-to-date</h3>
        <p class="meta">Real-time order ledger. Payments synced via Stripe + bank webhooks. Disputes auto-routed to Finance.</p>
      </div>
    </div>

    <div class="kpi-row">
      <div class="card kpi">
        <div class="kk">GMV · MTD</div>
        <div class="kv grad-text">{{ money(summary.gmv, { compact: true }) }}</div>
        <div class="kd up">▲ +14% MoM</div>
      </div>
      <div class="card kpi">
        <div class="kk">Outstanding</div>
        <div class="kv">{{ money(summary.outstanding, { compact: true }) }}</div>
        <div class="kd dimc">{{ orders.filter(o => o.pay !== 'paid').length }} orders pending</div>
      </div>
      <div class="card kpi">
        <div class="kk">Overdue</div>
        <div class="kv" :class="summary.overdue > 0 ? 'danger' : ''">{{ money(summary.overdue, { compact: true }) }}</div>
        <div class="kd dimc">{{ orders.filter(o => o.pay === 'overdue').length }} order(s)</div>
      </div>
      <div class="card kpi">
        <div class="kk">Avg ticket</div>
        <div class="kv">{{ money(summary.gmv / orders.length) }}</div>
        <div class="kd dimc">across {{ orders.length }} orders</div>
      </div>
    </div>

    <div class="card filters">
      <div class="search">
        <span class="ico">🔎</span>
        <input v-model="query" placeholder="Search order ID or partner name…" />
      </div>
      <div class="fl">
        <div class="fg">
          <span class="kicker">Payment</span>
          <div class="ch">
            <button v-for="p in payStates" :key="p" :class="{ on: filterPay === p }" @click="filterPay = p" type="button">{{ p }}</button>
          </div>
        </div>
        <div class="fg">
          <span class="kicker">Fulfillment</span>
          <div class="ch">
            <button v-for="f in fulStates" :key="f" :class="{ on: filterFul === f }" @click="filterFul = f" type="button">{{ f }}</button>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="th-row">
        <h3>Orders · {{ sorted.length }}</h3>
        <button class="btn btn-ghost sm" type="button" @click="exportCsv">Export CSV</button>
      </div>
      <table class="t">
        <thead>
          <tr>
            <th v-for="c in COLUMNS" :key="c.key" :class="{ num: c.num }" :aria-sort="ariaSort(c.key)">
              <button class="sort-h" type="button" @click="sortBy(c.key)">
                {{ c.label }}<span class="sort-g" aria-hidden="true">{{ sortGlyph(c.key) }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in sorted" :key="o.id">
            <td>
              <div class="o-id">{{ o.id }}</div>
              <div class="o-date">{{ o.placed }}</div>
            </td>
            <td>{{ o.partner }}</td>
            <td><span class="mk">{{ o.market }}</span></td>
            <td class="num">{{ o.items }}</td>
            <td class="num"><strong>{{ money(o.total) }}</strong></td>
            <td><span class="pay" :class="o.pay">{{ o.pay }}</span></td>
            <td><span class="ful" :class="o.fulfill">{{ o.fulfill }}</span></td>
            <td class="dimc">{{ o.due }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.ob { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; font-weight: 700; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi { padding: 16px 18px; }
.kk { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.kv { font-size: 24px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; margin: 8px 0 4px; }
.kv.danger { color: var(--danger); }
.kd { font-size: 11px; }
.kd.up { color: var(--success); }
.kd.dimc { color: var(--text-dim); }

.filters { padding: 14px 16px; display: flex; flex-direction: column; gap: 12px; }
.search { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
.search:focus-within { border-color: var(--primary); }
.search input { background: transparent; border: 0; color: var(--text); outline: none; flex: 1; font-size: 14px; }
.ico { color: var(--text-dim); }
.fl { display: flex; gap: 24px; flex-wrap: wrap; }
.fg { display: flex; flex-direction: column; gap: 6px; }
.fg .ch { display: flex; gap: 4px; flex-wrap: wrap; }
.fg .ch button { padding: 4px 10px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); color: var(--text-dim); cursor: pointer; font-size: 11px; text-transform: capitalize; }
.fg .ch button.on { background: rgba(124, 92, 255, .2); border-color: var(--primary); color: #fff; }

.th-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.t { width: 100%; border-collapse: collapse; font-size: 13px; }
.t th { text-align: left; padding: 10px 8px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.t th.num { text-align: right; }
.t th .sort-h { display: inline-flex; align-items: center; gap: 5px; background: none; border: 0; padding: 0; margin: 0; font: inherit; color: inherit; text-transform: inherit; letter-spacing: inherit; font-weight: inherit; cursor: pointer; }
.t th.num .sort-h { flex-direction: row-reverse; }
.t th .sort-h:hover { color: var(--text); }
.t th .sort-h:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; border-radius: 3px; }
.t th[aria-sort="ascending"] .sort-h, .t th[aria-sort="descending"] .sort-h { color: var(--primary-2); }
.sort-g { font-size: 8px; }
.t td { padding: 12px 8px; border-bottom: 1px dashed var(--border); }
.t td.num { text-align: right; font-variant-numeric: tabular-nums; }
.t td.dimc { color: var(--text-dim); }

.o-id { font-family: ui-monospace, monospace; color: var(--primary-2); font-weight: 700; font-size: 11px; }
.o-date { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
.mk { font-size: 10px; padding: 2px 7px; border-radius: 4px; background: var(--surface-2); font-weight: 700; }

.pay, .ful { font-size: 10px; padding: 3px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.pay.paid { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.pay.invoiced { background: rgba(96, 165, 250, .15); color: #93c5fd; }
.pay.overdue { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.ful.preparing { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.ful.shipped { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.ful.delivered { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.ful.on-hold { background: rgba(248, 113, 113, .15); color: #fca5a5; }

@media (max-width: 1024px) {
  .kpi-row { grid-template-columns: 1fr 1fr; }
  .t th:nth-child(3), .t td:nth-child(3),
  .t th:nth-child(8), .t td:nth-child(8) { display: none; }
}
</style>
