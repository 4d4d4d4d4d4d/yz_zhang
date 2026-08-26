<script setup>
import { ref, computed, watch } from 'vue'
import { conceptSignals, rankCandidates } from '../logic/recommend.js'

const product = ref('skincare')
const audience = ref(['gen-z', 'urban'])
const voice = ref('warm')
const goal = ref('roas')
const budget = ref(40000)

const productOpts = [
  { v: 'skincare', l: 'Skincare' },
  { v: 'sneaker', l: 'Sneakers' },
  { v: 'saas', l: 'SaaS' },
  { v: 'gadget', l: 'Consumer tech' },
  { v: 'food', l: 'Food / FMCG' }
]
const audienceOpts = [
  { v: 'gen-z', l: 'Gen Z' }, { v: 'millennial', l: 'Millennials' },
  { v: 'urban', l: 'Urban' }, { v: 'parents', l: 'Parents' },
  { v: 'professionals', l: 'Professionals' }, { v: 'students', l: 'Students' }
]
const voiceOpts = [
  { v: 'warm', l: 'Warm & humane' },
  { v: 'bold', l: 'Bold & punchy' },
  { v: 'clinical', l: 'Clinical & expert' },
  { v: 'playful', l: 'Playful' }
]
const goalOpts = [
  { v: 'roas', l: 'ROAS' }, { v: 'cpa', l: 'CPA' }, { v: 'reach', l: 'Reach' }
]

const thinkingSteps = [
  'Extracting visual signals from product image…',
  'Inferring audience clusters…',
  'Matching creative angles to brand voice…',
  'Selecting platform-native formats…',
  'Localizing for target markets…',
  'Scoring 1,284 candidate concepts…'
]
const step = ref(-1)
const computing = ref(false)
const showResults = ref(false)

function toggle(list, v) {
  const i = list.indexOf(v); if (i >= 0) list.splice(i, 1); else list.push(v)
}

async function run() {
  computing.value = true
  showResults.value = false
  step.value = -1
  for (let i = 0; i < thinkingSteps.length; i++) {
    await new Promise(r => setTimeout(r, 380))
    step.value = i
  }
  await new Promise(r => setTimeout(r, 220))
  computing.value = false
  showResults.value = true
}

watch([product, audience, voice, goal, budget], () => { showResults.value = false; step.value = -1 }, { deep: true })

// Spec 50 — concepts carry the targeting facts the ranker needs: which
// audiences they speak to, the brand voice they embody, and the production
// budget they require.
const CATALOG = {
  skincare: [
    { hook: 'Before / after reveal in 3 seconds', format: '9:16 reel', market: 'JP', ctr: 4.8, cvr: 3.2, roas: 4.1, audiences: ['gen-z', 'urban'], voice: 'clinical', minBudget: 20000, scores: { relevance: 94, creativity: 86, fit: 92, risk: 88 } },
    { hook: 'Founder POV — why we re-formulated', format: '1:1 carousel', market: 'US', ctr: 3.6, cvr: 2.7, roas: 3.4, audiences: ['millennial', 'professionals'], voice: 'warm', minBudget: 15000, scores: { relevance: 88, creativity: 80, fit: 90, risk: 92 } },
    { hook: '7-day skin diary (UGC)', format: '9:16 reel', market: 'KR', ctr: 5.2, cvr: 2.9, roas: 3.8, audiences: ['gen-z', 'students'], voice: 'playful', minBudget: 8000, scores: { relevance: 92, creativity: 90, fit: 88, risk: 84 } }
  ],
  sneaker: [
    { hook: 'Style swap montage', format: '9:16 reel', market: 'US', ctr: 5.1, cvr: 2.4, roas: 3.2, audiences: ['gen-z', 'urban'], voice: 'bold', minBudget: 18000, scores: { relevance: 92, creativity: 88, fit: 90, risk: 86 } },
    { hook: 'Build close-up + spec overlay', format: '16:9 demo', market: 'DE', ctr: 3.2, cvr: 2.8, roas: 3.0, audiences: ['professionals', 'millennial'], voice: 'clinical', minBudget: 30000, scores: { relevance: 86, creativity: 78, fit: 84, risk: 92 } },
    { hook: 'Street interview reactions', format: '9:16 reel', market: 'JP', ctr: 4.6, cvr: 2.2, roas: 2.8, audiences: ['gen-z', 'urban'], voice: 'playful', minBudget: 12000, scores: { relevance: 88, creativity: 90, fit: 86, risk: 80 } }
  ],
  saas: [
    { hook: 'Pain → workflow in 12 seconds', format: '16:9 demo', market: 'US', ctr: 2.8, cvr: 4.6, roas: 6.2, audiences: ['professionals'], voice: 'clinical', minBudget: 25000, scores: { relevance: 94, creativity: 76, fit: 92, risk: 96 } },
    { hook: 'Animated explainer · 30s', format: '1:1 feed', market: 'EU', ctr: 2.4, cvr: 3.8, roas: 4.4, audiences: ['professionals', 'millennial'], voice: 'warm', minBudget: 35000, scores: { relevance: 88, creativity: 84, fit: 88, risk: 94 } },
    { hook: 'Customer logo wall + ROI quote', format: '9:16 reel', market: 'BR', ctr: 3.0, cvr: 3.2, roas: 3.8, audiences: ['professionals'], voice: 'bold', minBudget: 15000, scores: { relevance: 84, creativity: 70, fit: 86, risk: 92 } }
  ],
  gadget: [
    { hook: 'Hand-held demo, 6s bumper', format: '6s bumper', market: 'US', ctr: 4.2, cvr: 2.1, roas: 2.6, audiences: ['gen-z', 'urban'], voice: 'bold', minBudget: 12000, scores: { relevance: 90, creativity: 82, fit: 88, risk: 90 } },
    { hook: 'Spec battle vs. competitor', format: '16:9 demo', market: 'DE', ctr: 3.4, cvr: 2.4, roas: 2.8, audiences: ['professionals', 'millennial'], voice: 'clinical', minBudget: 28000, scores: { relevance: 86, creativity: 74, fit: 84, risk: 78 } },
    { hook: 'Unboxing ASMR cut', format: '9:16 reel', market: 'JP', ctr: 5.0, cvr: 1.9, roas: 2.4, audiences: ['gen-z', 'students'], voice: 'playful', minBudget: 10000, scores: { relevance: 88, creativity: 92, fit: 88, risk: 86 } }
  ],
  food: [
    { hook: 'Recipe in 6 seconds', format: '6s bumper', market: 'US', ctr: 4.6, cvr: 2.0, roas: 2.6, audiences: ['parents', 'millennial'], voice: 'warm', minBudget: 9000, scores: { relevance: 92, creativity: 88, fit: 86, risk: 92 } },
    { hook: 'POV taste test', format: '9:16 reel', market: 'SEA', ctr: 4.2, cvr: 2.4, roas: 2.8, audiences: ['gen-z', 'students'], voice: 'playful', minBudget: 8000, scores: { relevance: 88, creativity: 86, fit: 90, risk: 86 } },
    { hook: 'Local cuisine pairing', format: '1:1 feed', market: 'JP', ctr: 3.8, cvr: 2.6, roas: 3.0, audiences: ['millennial', 'urban'], voice: 'warm', minBudget: 14000, scores: { relevance: 90, creativity: 84, fit: 92, risk: 90 } }
  ]
}

const SIGNAL_LABEL = {
  affinity: 'Audience affinity', freshness: 'Creative freshness',
  performance: 'Expected performance', brandFit: 'Brand-voice fit', localization: 'Market fit'
}

// Ranked by the spec-01 engine: weighted signals + MMR-lite diversity re-rank,
// with the per-signal contributions that make the ranking explainable.
const concepts = computed(() => {
  const base = CATALOG[product.value]
  const ctx = { audience: audience.value, voice: voice.value, goal: goal.value, budget: budget.value }
  const ranked = rankCandidates(
    base.map(c => ({ ...c, id: c.hook, signals: conceptSignals(c, ctx) })),
    { diversityPenalty: 0.15 }
  )
  return ranked.map(r => {
    const src = base.find(b => b.hook === r.id)
    return {
      ...src,
      total: Math.round(r.score),
      rank: r.rank,
      demoted: r.adjusted < r.score - 0.01,
      explanation: r.explanation
    }
  })
})

const signals = computed(() => [
  { tag: 'Category', value: productOpts.find(p => p.v === product.value).l, weight: 32 },
  { tag: 'Audience', value: audience.value.map(a => audienceOpts.find(x => x.v === a)?.l).join(' · ') || '—', weight: 26 },
  { tag: 'Brand voice', value: voiceOpts.find(v => v.v === voice.value).l, weight: 18 },
  { tag: 'Goal', value: goalOpts.find(g => g.v === goal.value).l, weight: 14 },
  { tag: 'Budget tier', value: budget.value >= 60000 ? 'Premium' : budget.value >= 20000 ? 'Growth' : 'Starter', weight: 10 }
])
</script>

<template>
  <div class="rec2">
    <div class="card panel inputs">
      <div class="kicker">Inputs</div>

      <div class="grp">
        <label>Product</label>
        <div class="chips">
          <button v-for="p in productOpts" :key="p.v" class="chip" :class="{ on: product === p.v }" @click="product = p.v" type="button">{{ p.l }}</button>
        </div>
      </div>

      <div class="grp">
        <label>Audience hints</label>
        <div class="chips">
          <button v-for="a in audienceOpts" :key="a.v" class="chip" :class="{ on: audience.includes(a.v) }" @click="toggle(audience, a.v)" type="button">{{ a.l }}</button>
        </div>
      </div>

      <div class="grp">
        <label>Brand voice</label>
        <div class="chips">
          <button v-for="v in voiceOpts" :key="v.v" class="chip" :class="{ on: voice === v.v }" @click="voice = v.v" type="button">{{ v.l }}</button>
        </div>
      </div>

      <div class="grp two">
        <div>
          <label>Goal</label>
          <div class="chips">
            <button v-for="g in goalOpts" :key="g.v" class="chip sm" :class="{ on: goal === g.v }" @click="goal = g.v" type="button">{{ g.l }}</button>
          </div>
        </div>
        <div>
          <label>Budget · ${{ budget.toLocaleString() }}</label>
          <input type="range" min="5000" max="200000" step="1000" v-model.number="budget" aria-label="Campaign budget" />
        </div>
      </div>

      <button class="btn btn-primary go" :disabled="computing" @click="run" type="button">
        <span v-if="computing">Reasoning…</span>
        <span v-else>Generate recommendations →</span>
      </button>

      <div class="signals">
        <div class="kicker">Signal attribution</div>
        <div v-for="s in signals" :key="s.tag" class="sig">
          <div class="srow"><span>{{ s.tag }}</span><span class="sval">{{ s.value }}</span></div>
          <div class="track"><div class="bar" :style="{ width: s.weight + '%' }"></div></div>
        </div>
      </div>
    </div>

    <div class="right">
      <div class="card trace" v-if="computing || step >= 0">
        <div class="kicker">AI trace</div>
        <ol>
          <li v-for="(t, i) in thinkingSteps" :key="i" :class="{ done: step >= i, active: step === i && computing }">
            <span class="dot"></span><span>{{ t }}</span>
          </li>
        </ol>
      </div>

      <transition name="fade">
        <div v-if="showResults" class="results">
          <div v-for="(c, i) in concepts" :key="i" class="card concept" :class="{ top: i === 0 }">
            <div class="head">
              <div class="rank">#{{ i + 1 }}</div>
              <div class="title">
                <h3>{{ c.hook }}</h3>
                <div class="meta">
                  {{ c.format }} · {{ c.market }} · score {{ c.total }}
                  <span v-if="c.demoted" class="dv" title="Demoted by the diversity re-rank so one format cannot sweep the top results">diversity re-rank</span>
                </div>
              </div>
              <div class="kpis">
                <div><div class="kn">{{ c.ctr.toFixed(1) }}%</div><div class="kl">CTR</div></div>
                <div><div class="kn">{{ c.cvr.toFixed(1) }}%</div><div class="kl">CVR</div></div>
                <div><div class="kn grad-text">{{ c.roas.toFixed(1) }}×</div><div class="kl">ROAS</div></div>
              </div>
            </div>
            <div class="why">Why this ranks here — contribution to the {{ c.total }} score</div>
            <div class="bars">
              <div v-for="e in c.explanation" :key="e.key" class="b">
                <div class="bl">
                  <span>{{ SIGNAL_LABEL[e.key] }}</span>
                  <span>{{ e.contribution.toFixed(1) }} pts</span>
                </div>
                <div class="bt"><div class="bf" :style="{ width: (e.contribution / 30 * 100) + '%' }"></div></div>
                <div class="bmeta">signal {{ (e.value * 100).toFixed(0) }}% × weight {{ (e.weight * 100).toFixed(0) }}%</div>
              </div>
            </div>
            <div class="actions">
              <button class="btn btn-primary" type="button">Use this concept</button>
              <button class="btn btn-ghost" type="button">Tune</button>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<style scoped>
.rec2 { display: grid; grid-template-columns: 1fr 1.4fr; gap: 20px; align-items: flex-start; }
.panel { display: flex; flex-direction: column; gap: 18px; }
.kicker { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.grp label { display: block; font-size: 12px; color: var(--text-dim); margin-bottom: 8px; }
.grp.two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { padding: 7px 12px; border-radius: 999px; background: var(--surface); color: var(--text); border: 1px solid var(--border); cursor: pointer; font-size: 12px; }
.chip.sm { padding: 6px 10px; font-size: 11px; }
.chip.on { background: rgba(124, 92, 255, .2); border-color: var(--primary); color: #fff; }
input[type="range"] { width: 100%; accent-color: var(--primary); }
.go { width: 100%; justify-content: center; }
.go:disabled { opacity: .7; cursor: not-allowed; }

.signals { padding-top: 16px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 12px; }
.sig .srow { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; }
.sig .sval { color: var(--text-dim); max-width: 60%; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track { height: 4px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.bar { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }

.right { display: flex; flex-direction: column; gap: 16px; }

.trace ol { list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 8px; }
.trace li { display: flex; align-items: center; gap: 10px; color: var(--text-dim); font-size: 13px; opacity: .55; }
.trace li.done { color: var(--text); opacity: 1; }
.trace li.active { color: #fff; }
.trace .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--surface-2); flex-shrink: 0; }
.trace li.done .dot { background: var(--success); box-shadow: 0 0 8px var(--success); }
.trace li.active .dot { background: var(--primary-2); box-shadow: 0 0 12px var(--primary-2); animation: p 1s ease-in-out infinite; }
@keyframes p { 0%,100% { opacity: 1; } 50% { opacity: .4; } }

.results { display: flex; flex-direction: column; gap: 14px; }
.concept .head { display: grid; grid-template-columns: auto 1fr auto; gap: 16px; align-items: center; margin-bottom: 16px; }
.rank { font-size: 22px; font-weight: 800; color: var(--text-dim); width: 44px; }
.concept.top { border-color: rgba(124, 92, 255, .5); background: linear-gradient(180deg, rgba(124,92,255,.1), rgba(34,211,238,.04)); }
.concept.top .rank { color: var(--primary-2); }
.title h3 { font-size: 17px; }
.meta { color: var(--text-dim); font-size: 12px; margin-top: 4px; }
.kpis { display: flex; gap: 18px; }
.kn { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
.kl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.why { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; font-weight: 700; margin-bottom: 8px; }
.dv { display: inline-block; margin-left: 8px; font-size: 10px; padding: 1px 7px; border-radius: 5px; background: rgba(251,191,36,.16); color: #fcd34d; }
.bmeta { font-size: 10px; color: var(--text-dim); margin-top: 3px; font-variant-numeric: tabular-nums; }
.bars { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 16px; }
@media (max-width: 900px) { .bars { grid-template-columns: repeat(2, 1fr); } }
.bl { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-dim); margin-bottom: 4px; text-transform: capitalize; }
.bt { height: 4px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.bf { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.actions { display: flex; gap: 10px; }

@media (max-width: 1024px) {
  .rec2 { grid-template-columns: 1fr; }
  .kpis { display: none; }
}
</style>
