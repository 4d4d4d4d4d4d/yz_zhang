<script setup>
import { ref, computed } from 'vue'

const stages = [
  { v: 'lead',      label: 'Lead',      color: '#94a3b8' },
  { v: 'qualified', label: 'Qualified', color: '#60a5fa' },
  { v: 'engaged',   label: 'Engaged',   color: '#7c5cff' },
  { v: 'proposal',  label: 'Proposal',  color: '#fbbf24' },
  { v: 'closed',    label: 'Closed',    color: '#34d399' }
]

const cards = ref([
  { id: 1, name: 'Lumen Studios',   stage: 'engaged',   region: 'JP', kind: 'Agency',    tier: 'Tier 1', value: 840, owner: 'AM',
    kyb: { id: 'ok', address: 'ok', bank: 'ok', counsel: 'pending', sanctions: 'ok' } },
  { id: 2, name: 'Aurora Media',    stage: 'proposal',  region: 'SG', kind: 'Media',     tier: 'Tier 1', value: 620, owner: 'KT',
    kyb: { id: 'ok', address: 'ok', bank: 'ok', counsel: 'ok', sanctions: 'ok' } },
  { id: 3, name: 'Northwave Partners', stage: 'closed', region: 'BR', kind: 'Distribution', tier: 'Tier 2', value: 1200, owner: 'AM',
    kyb: { id: 'ok', address: 'ok', bank: 'ok', counsel: 'ok', sanctions: 'ok' } },
  { id: 4, name: 'Cobalt Legal',    stage: 'engaged',   region: 'DE', kind: 'Compliance',tier: 'Tier 2', value: 220, owner: 'KT',
    kyb: { id: 'ok', address: 'ok', bank: 'ok', counsel: 'ok', sanctions: 'ok' } },
  { id: 5, name: 'Mizu Logistics',  stage: 'qualified', region: 'JP', kind: 'Logistics', tier: 'Tier 2', value: 380, owner: 'HM',
    kyb: { id: 'ok', address: 'pending', bank: 'pending', counsel: 'na', sanctions: 'ok' } },
  { id: 6, name: 'Helio Influencer',stage: 'lead',      region: 'BR', kind: 'Network',   tier: 'Tier 3', value: 95,  owner: 'AM',
    kyb: { id: 'pending', address: 'pending', bank: 'pending', counsel: 'na', sanctions: 'ok' } },
  { id: 7, name: 'Verda Commerce',  stage: 'qualified', region: 'SG', kind: 'Marketplace ops', tier: 'Tier 2', value: 540, owner: 'KT',
    kyb: { id: 'ok', address: 'ok', bank: 'pending', counsel: 'pending', sanctions: 'ok' } },
  { id: 8, name: 'Solace Studio',   stage: 'lead',      region: 'KR', kind: 'Agency',    tier: 'Tier 3', value: 140, owner: 'HM',
    kyb: { id: 'pending', address: 'pending', bank: 'na', counsel: 'na', sanctions: 'pending' } },
  { id: 9, name: 'Nimbus Labs',     stage: 'proposal',  region: 'US', kind: 'Tech',      tier: 'Tier 1', value: 980, owner: 'AM',
    kyb: { id: 'ok', address: 'ok', bank: 'ok', counsel: 'pending', sanctions: 'ok' } }
])

const query = ref('')
const facetRegion = ref('all')
const facetKind = ref('all')
const facetTier = ref('all')
const selected = ref(2)

const regions = ['all', 'JP', 'US', 'SG', 'DE', 'BR', 'KR']
const kinds   = ['all', 'Agency', 'Media', 'Distribution', 'Compliance', 'Logistics', 'Network', 'Marketplace ops', 'Tech']
const tiers   = ['all', 'Tier 1', 'Tier 2', 'Tier 3']

const visible = computed(() => cards.value.filter(c => {
  if (query.value && !c.name.toLowerCase().includes(query.value.toLowerCase())) return false
  if (facetRegion.value !== 'all' && c.region !== facetRegion.value) return false
  if (facetKind.value !== 'all' && c.kind !== facetKind.value) return false
  if (facetTier.value !== 'all' && c.tier !== facetTier.value) return false
  return true
}))

function colCards(stage) { return visible.value.filter(c => c.stage === stage) }
function colValue(stage) { return colCards(stage).reduce((s, c) => s + c.value, 0) }
function advance(c) {
  const i = stages.findIndex(s => s.v === c.stage)
  if (i < stages.length - 1) c.stage = stages[i + 1].v
}

const sel = computed(() => cards.value.find(c => c.id === selected.value))

const kybSteps = [
  { k: 'id',         label: 'Business identity',    info: 'Registration & ownership verified' },
  { k: 'address',    label: 'Address proof',        info: 'Recent utility / lease' },
  { k: 'bank',       label: 'Bank account',         info: 'Micro-deposit + payee match' },
  { k: 'counsel',    label: 'Counsel of record',    info: 'External legal point of contact' },
  { k: 'sanctions',  label: 'Sanctions screening',  info: 'OFAC / EU / UN watchlists' }
]
function kybStatus(c, k) { return c.kyb[k] }
function kybScore(c) {
  const vals = Object.values(c.kyb)
  const ok = vals.filter(v => v === 'ok').length
  const total = vals.filter(v => v !== 'na').length
  return total ? Math.round((ok / total) * 100) : 0
}
</script>

<template>
  <div class="pipe">
    <div class="card filters">
      <div class="search">
        <span class="ico">🔎</span>
        <input v-model="query" type="text" placeholder="Search partner name…" aria-label="Search partner name" />
      </div>
      <div class="facets">
        <div class="facet">
          <span class="kicker">Region</span>
          <div class="chips">
            <button v-for="r in regions" :key="r" :class="{ on: facetRegion === r }" @click="facetRegion = r" type="button">{{ r === 'all' ? 'All' : r }}</button>
          </div>
        </div>
        <div class="facet">
          <span class="kicker">Kind</span>
          <div class="chips">
            <button v-for="k in kinds" :key="k" :class="{ on: facetKind === k }" @click="facetKind = k" type="button">{{ k === 'all' ? 'All' : k }}</button>
          </div>
        </div>
        <div class="facet">
          <span class="kicker">Tier</span>
          <div class="chips">
            <button v-for="t in tiers" :key="t" :class="{ on: facetTier === t }" @click="facetTier = t" type="button">{{ t === 'all' ? 'All' : t }}</button>
          </div>
        </div>
      </div>
    </div>

    <div class="layout">
      <div class="board">
        <div v-for="s in stages" :key="s.v" class="col">
          <div class="col-head">
            <span class="col-name"><span class="col-dot" :style="{ background: s.color }"></span>{{ s.label }}</span>
            <span class="col-meta">{{ colCards(s.v).length }} · ${{ colValue(s.v) }}k</span>
          </div>
          <div class="col-body">
            <div v-for="c in colCards(s.v)" :key="c.id"
              class="ct" :class="{ on: selected === c.id }"
              @click="selected = c.id">
              <div class="ct-top">
                <span class="ct-name">{{ c.name }}</span>
                <span class="ct-tier">{{ c.tier }}</span>
              </div>
              <div class="ct-mid">
                <span>{{ c.kind }}</span><span>·</span><span>{{ c.region }}</span>
              </div>
              <div class="ct-bot">
                <span class="ct-val">${{ c.value }}k</span>
                <span class="ct-own">{{ c.owner }}</span>
                <button v-if="c.stage !== 'closed'" class="ct-next" @click.stop="advance(c)" type="button" title="Advance stage">→</button>
              </div>
            </div>
            <div v-if="!colCards(s.v).length" class="empty">No deals</div>
          </div>
        </div>
      </div>

      <aside class="card side" v-if="sel">
        <div class="sh">
          <h3>{{ sel.name }}</h3>
          <span class="stier">{{ sel.tier }}</span>
        </div>
        <div class="sm">{{ sel.kind }} · {{ sel.region }} · ${{ sel.value }}k ARR potential</div>

        <div class="kyb">
          <div class="kyb-head">
            <span class="kicker">KYB verification</span>
            <span class="kyb-score" :class="kybScore(sel) >= 80 ? 'ok' : kybScore(sel) >= 50 ? 'warn' : 'risk'">{{ kybScore(sel) }}%</span>
          </div>
          <div v-for="(step, i) in kybSteps" :key="step.k" class="kstep" :class="kybStatus(sel, step.k)">
            <div class="kindex">{{ i + 1 }}</div>
            <div class="kbody">
              <div class="klabel">{{ step.label }}</div>
              <div class="kinfo">{{ step.info }}</div>
            </div>
            <span class="kstatus" :class="kybStatus(sel, step.k)">
              {{ kybStatus(sel, step.k) === 'ok' ? '✓' : kybStatus(sel, step.k) === 'pending' ? '◷' : '—' }}
            </span>
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-primary" type="button">Open deal room</button>
          <button class="btn btn-ghost" type="button">Message</button>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.pipe { display: flex; flex-direction: column; gap: 16px; }

.filters { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.search { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
.search:focus-within { border-color: var(--primary); }
.search input { background: transparent; border: 0; color: var(--text); outline: none; flex: 1; font-size: 14px; }
.ico { color: var(--text-dim); }
.facets { display: flex; gap: 24px; flex-wrap: wrap; }
.facet { display: flex; flex-direction: column; gap: 6px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; font-weight: 700; }
.facet .chips { display: flex; gap: 4px; flex-wrap: wrap; }
.facet .chips button { padding: 4px 10px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); color: var(--text-dim); cursor: pointer; font-size: 11px; }
.facet .chips button.on { background: rgba(124, 92, 255, .2); border-color: var(--primary); color: #fff; }

.layout { display: grid; grid-template-columns: 1fr 320px; gap: 16px; align-items: flex-start; }
.board { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
.col { background: rgba(20, 20, 31, .35); border: 1px solid var(--border); border-radius: 12px; padding: 10px; min-height: 360px; }
.col-head { display: flex; justify-content: space-between; align-items: center; padding: 4px 6px 10px; border-bottom: 1px solid var(--border); margin-bottom: 8px; }
.col-name { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; }
.col-dot { width: 8px; height: 8px; border-radius: 50%; }
.col-meta { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.col-body { display: flex; flex-direction: column; gap: 8px; }

.ct { padding: 10px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; cursor: pointer; transition: border-color .15s; }
.ct:hover { border-color: var(--primary); }
.ct.on { border-color: var(--primary); background: rgba(124, 92, 255, .12); }
.ct-top { display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 4px; }
.ct-name { font-weight: 600; font-size: 13px; line-height: 1.3; }
.ct-tier { font-size: 9px; padding: 2px 6px; border-radius: 4px; background: var(--surface-2); color: var(--text-dim); text-transform: uppercase; letter-spacing: .05em; flex-shrink: 0; }
.ct-mid { display: flex; gap: 4px; font-size: 11px; color: var(--text-dim); margin-bottom: 6px; }
.ct-bot { display: flex; justify-content: space-between; align-items: center; font-size: 11px; }
.ct-val { font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.ct-own { color: var(--text-dim); font-size: 10px; padding: 2px 6px; border-radius: 50%; background: var(--surface-2); }
.ct-next { background: transparent; border: 1px solid var(--border); color: var(--text-dim); border-radius: 6px; padding: 2px 8px; cursor: pointer; font-size: 11px; }
.ct-next:hover { color: #fff; background: linear-gradient(135deg, var(--primary), var(--primary-2)); border: 0; }
.empty { padding: 20px 8px; text-align: center; font-size: 11px; color: var(--text-dim); border: 1px dashed var(--border); border-radius: 8px; }

.side { padding: 18px; position: sticky; top: 90px; }
.sh { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.stier { font-size: 11px; padding: 3px 8px; border-radius: 6px; background: var(--surface-2); color: var(--text-dim); }
.sm { color: var(--text-dim); font-size: 13px; margin-bottom: 16px; }

.kyb { padding-top: 16px; border-top: 1px solid var(--border); margin-bottom: 16px; }
.kyb-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.kyb-score { font-weight: 800; font-size: 14px; padding: 3px 10px; border-radius: 6px; }
.kyb-score.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.kyb-score.warn { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.kyb-score.risk { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.kstep { display: grid; grid-template-columns: 22px 1fr auto; gap: 10px; align-items: center; padding: 10px 0; border-bottom: 1px dashed var(--border); }
.kstep:last-of-type { border-bottom: 0; }
.kindex { width: 22px; height: 22px; border-radius: 50%; background: var(--surface-2); color: var(--text-dim); display: grid; place-items: center; font-size: 11px; font-weight: 700; }
.kstep.ok .kindex { background: var(--success); color: #0a0a0f; }
.kstep.pending .kindex { background: #fcd34d; color: #0a0a0f; }
.klabel { font-size: 13px; font-weight: 500; }
.kinfo { font-size: 11px; color: var(--text-dim); }
.kstatus { font-size: 14px; font-weight: 700; }
.kstatus.ok { color: var(--success); }
.kstatus.pending { color: #fcd34d; }
.kstatus.na { color: var(--text-dim); }

.actions { display: flex; gap: 8px; }
.actions :deep(.btn) { flex: 1; justify-content: center; }

@media (max-width: 1200px) {
  .board { grid-template-columns: repeat(3, 1fr); }
  .layout { grid-template-columns: 1fr; }
  .side { position: static; }
}
@media (max-width: 720px) {
  .board { grid-template-columns: 1fr; }
}
</style>
