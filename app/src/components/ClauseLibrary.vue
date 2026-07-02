<script setup>
import { ref, computed } from 'vue'

const query = ref('')
const category = ref('all')

const clauses = [
  { id: 'EX-01', title: 'Exclusivity · brick-and-mortar carve-out', cat: 'commercial', usage: 142, winRate: 78, risk: 'med',
    body: 'Distributor shall have exclusive rights to sell the Products through physical retail channels in the Territory for a period of twenty-four (24) months. Direct-to-consumer e-commerce and Supplier-owned channels are expressly excluded from this exclusivity.',
    fallbacks: ['non-exclusive', '12-month exclusive (full)', '36-month with renewal review'] },
  { id: 'PR-01', title: 'Pricing · MSRP-48 with rebate gate',       cat: 'commercial', usage: 198, winRate: 84, risk: 'low',
    body: 'Distributor shall purchase Products at MSRP less forty-eight percent (48%), with a four percent (4%) quarterly rebate on volumes above 5,000 units.',
    fallbacks: ['MSRP-45 flat', 'MSRP-50 with 6% rebate', 'sliding rebate ladder'] },
  { id: 'IP-01', title: 'IP indemnity · mutual capped',             cat: 'legal', usage: 220, winRate: 91, risk: 'low',
    body: 'Each party shall indemnify the other for infringement of third-party IP rights arising from such party\'s Materials, capped at twelve (12) months of fees paid hereunder.',
    fallbacks: ['mutual uncapped', 'one-sided to Supplier', 'cap = 24 months fees'] },
  { id: 'DP-01', title: 'Data · APPI-compliant DPA',                cat: 'privacy', usage: 88, winRate: 95, risk: 'low',
    body: 'The parties shall enter into a Data Processing Agreement compliant with the Act on the Protection of Personal Information (APPI). All Personal Data shall be hosted in approved Japanese data centers unless SCCs are executed.',
    fallbacks: ['GDPR SCC equivalence', 'mutual DPA only', 'no cross-border transfer'] },
  { id: 'AI-01', title: 'AI provenance · C2PA disclosure',          cat: 'ai',     usage: 41, winRate: 88, risk: 'low',
    body: 'All AI-generated Materials shall carry C2PA provenance signatures. Materials shall be labeled as AI-generated in all jurisdictions where such disclosure is required.',
    fallbacks: ['disclosure on request only', 'opt-in labeling', 'full provenance + audit logs'] },
  { id: 'TM-01', title: 'Term · 24 mo · 90-day for cause',          cat: 'commercial', usage: 168, winRate: 76, risk: 'med',
    body: 'Initial term shall be twenty-four (24) months. Either party may terminate for cause on ninety (90) days written notice, or for convenience on one hundred eighty (180) days notice.',
    fallbacks: ['12 mo · 60-day notice', '36 mo · 12-month notice', 'evergreen with annual review'] },
  { id: 'LB-01', title: 'Liability · capped at 12 mo fees',         cat: 'legal',  usage: 196, winRate: 82, risk: 'low',
    body: 'Total aggregate liability shall not exceed the fees paid in the twelve (12) months immediately preceding the event giving rise to the claim, excluding indemnification obligations.',
    fallbacks: ['cap = 6 mo fees', 'cap = 24 mo fees', 'no cap for breach of confidentiality'] },
  { id: 'CF-01', title: 'Confidentiality · 5-year mutual',          cat: 'legal',  usage: 240, winRate: 96, risk: 'low',
    body: 'Each party shall hold the other party\'s Confidential Information in confidence for a period of five (5) years from disclosure, with industry-standard exceptions.',
    fallbacks: ['3-year mutual', 'indefinite for trade secrets', 'perpetual mutual'] }
]

const cats = ['all', 'commercial', 'legal', 'privacy', 'ai']

const filtered = computed(() => clauses.filter(c => {
  if (category.value !== 'all' && c.cat !== category.value) return false
  if (query.value && !(c.title + ' ' + c.body).toLowerCase().includes(query.value.toLowerCase())) return false
  return true
}))

const selected = ref(clauses[0].id)
const cur = computed(() => clauses.find(c => c.id === selected.value))
</script>

<template>
  <div class="lib">
    <div class="card filters">
      <div class="search">
        <span class="ico">🔎</span>
        <input v-model="query" type="text" placeholder="Search 240+ clauses…" />
      </div>
      <div class="cats">
        <button v-for="c in cats" :key="c" :class="{ on: category === c }" @click="category = c" type="button">{{ c }}</button>
      </div>
    </div>

    <div class="grid">
      <div class="card list-col">
        <div class="hh">
          <h3>{{ filtered.length }} clauses</h3>
          <span class="meta">Sorted by usage</span>
        </div>
        <div class="list">
          <button v-for="c in filtered" :key="c.id"
            class="li" :class="{ on: selected === c.id }"
            @click="selected = c.id" type="button">
            <div class="li-top">
              <span class="li-id">{{ c.id }}</span>
              <span class="li-cat" :class="c.cat">{{ c.cat }}</span>
            </div>
            <div class="li-title">{{ c.title }}</div>
            <div class="li-stats">
              <span>{{ c.usage }} deals</span>
              <span class="dot">·</span>
              <span class="win">{{ c.winRate }}% accepted</span>
              <span class="dot">·</span>
              <span class="risk" :class="c.risk">{{ c.risk }} risk</span>
            </div>
          </button>
        </div>
      </div>

      <div class="card detail">
        <div class="d-head">
          <div>
            <div class="kicker">{{ cur.id }} · {{ cur.cat }}</div>
            <h3>{{ cur.title }}</h3>
          </div>
          <div class="d-stats">
            <div><div class="dn grad-text">{{ cur.winRate }}%</div><div class="dl">accepted</div></div>
            <div><div class="dn">{{ cur.usage }}</div><div class="dl">deals used</div></div>
          </div>
        </div>

        <div class="kicker">Primary text</div>
        <div class="doc">{{ cur.body }}</div>

        <div class="kicker">Fallback positions · ordered by softness</div>
        <ol class="fallbacks">
          <li v-for="(f, i) in cur.fallbacks" :key="i">
            <span class="fi">{{ i + 1 }}</span>
            <span>{{ f }}</span>
            <button class="mini" type="button">Use</button>
          </li>
        </ol>

        <div class="d-actions">
          <button class="btn btn-primary sm" type="button">Insert into current deal →</button>
          <button class="btn btn-ghost sm" type="button">View 12 redlined precedents</button>
          <button class="btn btn-ghost sm" type="button">Copy</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lib { display: flex; flex-direction: column; gap: 16px; }
.filters { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.search { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
.search:focus-within { border-color: var(--primary); }
.search input { background: transparent; border: 0; color: var(--text); outline: none; flex: 1; font-size: 14px; }
.ico { color: var(--text-dim); }
.cats { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; width: max-content; }
.cats button { padding: 5px 12px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 12px; text-transform: capitalize; }
.cats button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.grid { display: grid; grid-template-columns: 1fr 1.4fr; gap: 16px; align-items: flex-start; }
.hh { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; }
.meta { color: var(--text-dim); font-size: 12px; }

.list { display: flex; flex-direction: column; gap: 6px; max-height: 540px; overflow-y: auto; }
.li { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); cursor: pointer; text-align: left; color: var(--text); }
.li:hover { border-color: var(--primary); }
.li.on { border-color: var(--primary); background: rgba(124, 92, 255, .1); }
.li-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.li-id { font-family: ui-monospace, monospace; font-size: 10px; color: var(--primary-2); font-weight: 700; }
.li-cat { font-size: 9px; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: .05em; font-weight: 700; }
.li-cat.commercial { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.li-cat.legal { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.li-cat.privacy { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.li-cat.ai { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.li-title { font-size: 13px; font-weight: 600; margin-bottom: 6px; line-height: 1.35; }
.li-stats { display: flex; gap: 6px; font-size: 11px; color: var(--text-dim); align-items: center; }
.li-stats .dot { color: var(--border); }
.li-stats .win { color: var(--success); }
.risk { padding: 1px 6px; border-radius: 4px; font-weight: 700; }
.risk.low { background: rgba(52, 211, 153, .12); color: #6ee7b7; }
.risk.med { background: rgba(251, 191, 36, .12); color: #fcd34d; }

.detail { padding: 20px; position: sticky; top: 90px; }
.d-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin-bottom: 16px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-top: 14px; margin-bottom: 8px; font-weight: 700; }
.d-stats { display: flex; gap: 16px; text-align: right; }
.dn { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.dl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.doc { padding: 14px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; font-family: ui-serif, Georgia, serif; font-size: 13px; line-height: 1.7; color: var(--text); }

.fallbacks { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
.fallbacks li { display: grid; grid-template-columns: 24px 1fr auto; gap: 10px; align-items: center; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); font-size: 13px; }
.fi { width: 22px; height: 22px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; font-size: 11px; font-weight: 700; color: var(--text-dim); }
.mini { padding: 4px 10px; border-radius: 6px; background: var(--surface-2); border: 1px solid var(--border); color: var(--text); font-size: 11px; cursor: pointer; }
.mini:hover { border-color: var(--primary); }

.d-actions { display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; }
  .detail { position: static; }
}
</style>
