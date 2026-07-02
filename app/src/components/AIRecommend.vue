<script setup>
import { ref, computed } from 'vue'

const category = ref('beauty')
const budget = ref(20000)
const goal = ref('roas')

const categories = [
  { v: 'beauty', label: 'Beauty / DTC' },
  { v: 'saas', label: 'SaaS / B2B' },
  { v: 'fashion', label: 'Fashion' },
  { v: 'tech', label: 'Consumer tech' },
  { v: 'food', label: 'Food / FMCG' }
]
const goals = [
  { v: 'roas', label: 'Maximize ROAS' },
  { v: 'cpa', label: 'Lower CPA' },
  { v: 'reach', label: 'Brand reach' },
  { v: 'launch', label: 'New market launch' }
]

const matrix = {
  beauty: { hooks: ['Before/after reveal', 'UGC unboxing', 'Founder POV'], formats: ['9:16 short', 'Carousel', '6s bumper'], markets: ['JP', 'KR', 'US', 'SEA'] },
  saas: { hooks: ['Pain → demo', 'Workflow speed', 'Customer logos'], formats: ['16:9 demo', 'Animated explainer', 'Vertical testimonial'], markets: ['US', 'EU', 'BR', 'IN'] },
  fashion: { hooks: ['Style swap', 'Editorial cut', 'Lookbook reel'], formats: ['9:16 reel', '1:1 grid', 'Stories ad'], markets: ['US', 'EU', 'JP', 'MX'] },
  tech: { hooks: ['Spec overlay', 'Hand demo', 'Comparison cut'], formats: ['9:16', '16:9', '4:5'], markets: ['US', 'EU', 'JP', 'IN'] },
  food: { hooks: ['Recipe in 6s', 'POV taste', 'Local context'], formats: ['9:16', '1:1', '6s bumper'], markets: ['US', 'JP', 'SEA', 'EU'] }
}

const recs = computed(() => {
  const m = matrix[category.value]
  const conf = goal.value === 'launch' ? 0.78 : goal.value === 'reach' ? 0.83 : 0.91
  return {
    hooks: m.hooks,
    formats: m.formats,
    markets: m.markets,
    spend: Math.round(budget.value / m.markets.length),
    variants: Math.min(60, Math.round(budget.value / 800)),
    confidence: Math.round(conf * 100)
  }
})
</script>

<template>
  <div class="rec">
    <div class="card panel">
      <div class="row">
        <label>Product category</label>
        <div class="chips">
          <button v-for="c in categories" :key="c.v"
            class="chip" :class="{ on: category === c.v }"
            @click="category = c.v" type="button">{{ c.label }}</button>
        </div>
      </div>
      <div class="row">
        <label>Monthly budget · USD</label>
        <div class="range">
          <input type="range" min="2000" max="200000" step="1000" v-model.number="budget" />
          <span class="amount">${{ budget.toLocaleString() }}</span>
        </div>
      </div>
      <div class="row">
        <label>Goal</label>
        <div class="chips">
          <button v-for="g in goals" :key="g.v"
            class="chip" :class="{ on: goal === g.v }"
            @click="goal = g.v" type="button">{{ g.label }}</button>
        </div>
      </div>
    </div>

    <div class="card output">
      <div class="head">
        <div>
          <div class="eyebrow">AI recommendation</div>
          <h3>Suggested plan</h3>
        </div>
        <div class="conf">
          <div class="conf-num">{{ recs.confidence }}%</div>
          <div class="conf-lbl">confidence</div>
        </div>
      </div>

      <div class="grid grid-2">
        <div>
          <div class="kicker">Top hooks</div>
          <ul>
            <li v-for="h in recs.hooks" :key="h">{{ h }}</li>
          </ul>
        </div>
        <div>
          <div class="kicker">Recommended formats</div>
          <ul>
            <li v-for="f in recs.formats" :key="f">{{ f }}</li>
          </ul>
        </div>
        <div>
          <div class="kicker">Target markets</div>
          <div class="tags">
            <span v-for="m in recs.markets" :key="m" class="tag">{{ m }}</span>
          </div>
        </div>
        <div>
          <div class="kicker">Plan summary</div>
          <ul>
            <li><strong>{{ recs.variants }}</strong> creative variants</li>
            <li>≈ <strong>${{ recs.spend.toLocaleString() }}</strong> / market / month</li>
            <li>First wave in <strong>72h</strong></li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rec { display: grid; grid-template-columns: 1fr 1.2fr; gap: 20px; }
.panel { display: flex; flex-direction: column; gap: 22px; }
.row label { display: block; font-size: 12px; color: var(--text-dim); margin-bottom: 10px; text-transform: uppercase; letter-spacing: .08em; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; }
.chip { padding: 8px 14px; border-radius: 999px; background: var(--surface); color: var(--text); border: 1px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.on { background: rgba(124, 92, 255, .2); border-color: var(--primary); color: #fff; }
.range { display: flex; align-items: center; gap: 14px; }
.range input { flex: 1; accent-color: var(--primary); }
.amount { font-weight: 700; font-variant-numeric: tabular-nums; min-width: 100px; text-align: right; }

.output .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; margin-bottom: 20px; }
.conf { text-align: right; }
.conf-num { font-size: 32px; font-weight: 800; color: var(--success); }
.conf-lbl { font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.kicker { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 8px; }
.output ul { margin: 0; padding-left: 18px; color: var(--text); }
.output li { margin: 4px 0; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
.tag { padding: 4px 10px; border-radius: 6px; background: var(--surface-2); font-size: 12px; color: var(--text); border: 1px solid var(--border); }

@media (max-width: 900px) { .rec { grid-template-columns: 1fr; } }
</style>
