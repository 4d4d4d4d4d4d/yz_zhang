<script setup>
import { ref, computed } from 'vue'
import { rankPartners } from '../logic/matching.js'

const category = ref('beauty')
const market = ref('JP')
const stage = ref('launch')

const categories = ['beauty', 'fashion', 'tech', 'saas', 'food']
const markets = ['JP', 'KR', 'US', 'BR', 'DE', 'SEA']
const stages = [
  { v: 'discovery', label: 'Discovery' },
  { v: 'launch', label: 'First launch' },
  { v: 'scale', label: 'Scaling' }
]

// Spec 13 R3: one scoring engine everywhere — this DB feeds spec 03's
// rankPartners. Editorial score maps to the trust factor.
const partnerDB = [
  { id: 'lumen',  name: 'Lumen Studios', kind: 'Creative agency', stage: 'growth', regions: ['JP', 'KR'], cats: ['beauty', 'fashion'], score: 94, note: 'Tokyo-based, won 2024 Spikes Asia for Shiseido relaunch.' },
  { id: 'aurora', name: 'Aurora Media', kind: 'Media buying', stage: 'scale', regions: ['JP', 'SEA'], cats: ['beauty', 'food'], score: 91, note: 'Managed $40M in beauty DTC in APAC last year.' },
  { id: 'north',  name: 'Northwave Partners', kind: 'Distributor', stage: 'scale', regions: ['US', 'BR'], cats: ['saas', 'tech'], score: 88, note: 'B2B SaaS distribution across the Americas.' },
  { id: 'mizu',   name: 'Mizu Logistics', kind: '3PL', stage: 'enterprise', regions: ['JP', 'KR', 'SEA'], cats: ['beauty', 'fashion', 'food'], score: 85, note: 'Same-day fulfillment from Osaka and Singapore.' },
  { id: 'helio',  name: 'Helio Influencer', kind: 'Influencer network', stage: 'growth', regions: ['BR', 'MX', 'US'], cats: ['fashion', 'beauty'], score: 82, note: '12k creators across LATAM, fluent in PT/ES.' },
  { id: 'cobalt', name: 'Cobalt Legal', kind: 'Compliance partner', stage: 'enterprise', regions: ['DE', 'US', 'JP'], cats: ['saas', 'tech', 'beauty'], score: 90, note: 'GDPR / CCPA / APPI advisory, cross-border DPAs.' },
  { id: 'verda',  name: 'Verda Commerce', kind: 'Marketplace ops', stage: 'growth', regions: ['JP', 'SEA'], cats: ['beauty', 'fashion', 'tech'], score: 80, note: 'Rakuten + Shopee onboarding in <14 days.' }
]

const STAGE_MAP = { discovery: 'seed', launch: 'growth', scale: 'scale' }

const matches = computed(() => {
  const need = { categories: [category.value], markets: [market.value], stage: STAGE_MAP[stage.value] }
  const partners = partnerDB.map(p => ({
    id: p.id, categories: p.cats, markets: p.regions, stage: p.stage, trust: p.score / 100, meta: p
  }))
  return rankPartners(need, partners, { topN: 5, includeWeak: true })
    .map(r => ({ ...r.partner.meta, matchScore: r.score, reasons: r.reasons }))
})
</script>

<template>
  <div class="match">
    <div class="card filters">
      <div class="f">
        <label>Category</label>
        <div class="chips">
          <button v-for="c in categories" :key="c" class="chip" :class="{ on: category === c }" @click="category = c" type="button">{{ c }}</button>
        </div>
      </div>
      <div class="f">
        <label>Target market</label>
        <div class="chips">
          <button v-for="m in markets" :key="m" class="chip" :class="{ on: market === m }" @click="market = m" type="button">{{ m }}</button>
        </div>
      </div>
      <div class="f">
        <label>Stage</label>
        <div class="chips">
          <button v-for="s in stages" :key="s.v" class="chip" :class="{ on: stage === s.v }" @click="stage = s.v" type="button">{{ s.label }}</button>
        </div>
      </div>
    </div>

    <div class="card list">
      <div class="head">
        <h3>{{ matches.length }} suggested partners</h3>
        <span class="meta">Ranked by category × market × stage fit</span>
      </div>
      <div v-for="p in matches" :key="p.name" class="row">
        <div class="row-left">
          <div class="logo" :style="{ background: `linear-gradient(135deg, hsl(${p.name.length * 24}, 80%, 65%), hsl(${(p.name.length * 24 + 60) % 360}, 80%, 55%))` }">{{ p.name[0] }}</div>
          <div>
            <div class="name">{{ p.name }}</div>
            <div class="kind">{{ p.kind }} · {{ p.regions.join(' / ') }}</div>
            <div class="note">{{ p.note }}</div>
          </div>
        </div>
        <div class="row-right">
          <div class="score" :class="p.matchScore >= 80 ? 'high' : p.matchScore >= 60 ? 'mid' : 'low'">{{ p.matchScore }}</div>
          <div class="score-lbl">match</div>
          <button class="btn btn-ghost intro" type="button">Request intro →</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.match { display: grid; grid-template-columns: 1fr 1.8fr; gap: 20px; }
.filters { display: flex; flex-direction: column; gap: 22px; }
.f label { display: block; font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 10px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { padding: 8px 14px; border-radius: 999px; background: var(--surface); color: var(--text); border: 1px solid var(--border); cursor: pointer; font-size: 13px; text-transform: capitalize; }
.chip.on { background: rgba(124, 92, 255, .2); border-color: var(--primary); color: #fff; }

.list .head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; }
.meta { color: var(--text-dim); font-size: 12px; }

.row { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 16px 0; border-bottom: 1px dashed var(--border); }
.row:last-child { border-bottom: 0; }
.row-left { display: flex; gap: 14px; flex: 1; min-width: 0; }
.logo { width: 44px; height: 44px; border-radius: 10px; display: grid; place-items: center; font-weight: 800; color: #0a0a0f; flex-shrink: 0; }
.name { font-weight: 700; }
.kind { font-size: 12px; color: var(--text-dim); margin-top: 2px; }
.note { font-size: 13px; color: var(--text); margin-top: 6px; }

.row-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
.score { font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums; }
.score.high { color: var(--success); }
.score.mid { color: #fcd34d; }
.score.low { color: var(--text-dim); }
.score-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.intro { margin-top: 6px; font-size: 12px; padding: 6px 12px; }

@media (max-width: 900px) {
  .match { grid-template-columns: 1fr; }
  .row { flex-direction: column; align-items: flex-start; }
  .row-right { flex-direction: row; align-items: center; align-self: stretch; }
  .score-lbl { display: none; }
}
</style>
