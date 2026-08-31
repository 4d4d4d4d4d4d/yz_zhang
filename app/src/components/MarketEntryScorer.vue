<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { rankMarkets, ATTRACTIVENESS, CAGE, FRICTION_CEILING } from '../logic/marketEntry.js'

const { t, locale } = useI18n()

// Candidate markets. Values are 0–1 indices against the best market in the
// set, which is how the underlying research reports them; absolute figures
// (TAM in dollars) sit in the tooltip layer, not the score.
const MARKETS = [
  { code: 'JP', flag: '🇯🇵', tam: 0.82, growth: 0.44, digital: 0.88, payments: 0.91, headroom: 0.52,
    distance: { cultural: 0.72, administrative: 0.48, geographic: 0.55, economic: 0.22 },
    cac: 4200, arpa: 520, grossMargin: 74 },
  { code: 'DE', flag: '🇩🇪', tam: 0.74, growth: 0.38, digital: 0.79, payments: 0.84, headroom: 0.41,
    distance: { cultural: 0.44, administrative: 0.62, geographic: 0.68, economic: 0.18 },
    cac: 3800, arpa: 610, grossMargin: 76 },
  { code: 'BR', flag: '🇧🇷', tam: 0.58, growth: 0.86, digital: 0.71, payments: 0.62, headroom: 0.78,
    distance: { cultural: 0.51, administrative: 0.74, geographic: 0.82, economic: 0.66 },
    cac: 2100, arpa: 240, grossMargin: 68 },
  { code: 'AE', flag: '🇦🇪', tam: 0.41, growth: 0.79, digital: 0.86, payments: 0.88, headroom: 0.69,
    distance: { cultural: 0.58, administrative: 0.35, geographic: 0.47, economic: 0.24 },
    cac: 3100, arpa: 780, grossMargin: 79 },
  { code: 'ID', flag: '🇮🇩', tam: 0.62, growth: 0.91, digital: 0.66, payments: 0.48, headroom: 0.83,
    distance: { cultural: 0.63, administrative: 0.68, geographic: 0.71, economic: 0.74 },
    cac: 1400, arpa: 145, grossMargin: 61 },
  { code: 'MX', flag: '🇲🇽', tam: 0.49, growth: 0.72, digital: 0.68, payments: 0.57, headroom: 0.74,
    distance: { cultural: 0.46, administrative: 0.55, geographic: 0.44, economic: 0.58 },
    cac: 1900, arpa: 265, grossMargin: 70 }
]

// The weights are the model. Exposing them is the difference between a ranking
// an operator can argue with and one they have to accept.
const ceiling = ref(FRICTION_CEILING)
const weights = ref({ ...ATTRACTIVENESS })

const ranked = computed(() => rankMarkets(MARKETS, {
  attractiveness: weights.value,
  ceiling: ceiling.value
}).map(r => ({ ...r, flag: MARKETS.find(m => m.code === r.code).flag })))

const selected = ref('JP')
const detail = computed(() => ranked.value.find(r => r.code === selected.value) ?? ranked.value[0])

function reset() {
  weights.value = { ...ATTRACTIVENESS }
  ceiling.value = FRICTION_CEILING
}
const changed = computed(() =>
  ceiling.value !== FRICTION_CEILING ||
  Object.entries(ATTRACTIVENESS).some(([k, v]) => weights.value[k] !== v))

const money = n => new Intl.NumberFormat(locale.value, {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0
}).format(n)

const ATTR_KEYS = Object.keys(ATTRACTIVENESS)
const CAGE_KEYS = Object.keys(CAGE)
</script>

<template>
  <div class="mes">
    <div class="card head">
      <div>
        <div class="kicker">{{ t('entry.kicker') }}</div>
        <h3>{{ t('entry.title') }}</h3>
        <p class="meta">{{ t('entry.sub') }}</p>
      </div>
      <div class="tot">
        <div class="tn grad-text">{{ ranked.filter(r => r.band === 'enter').length }}</div>
        <div class="tl">{{ t('entry.readyNow') }}</div>
      </div>
    </div>

    <div class="row">
      <div class="card list">
        <div class="th-row">
          <h3>{{ t('entry.ranking') }}</h3>
          <button v-if="changed" class="btn btn-ghost sm" type="button" @click="reset">{{ t('entry.reset') }}</button>
        </div>
        <button v-for="m in ranked" :key="m.code" type="button" class="mk"
          :class="{ on: m.code === selected }" @click="selected = m.code"
          :aria-pressed="m.code === selected">
          <span class="flag" aria-hidden="true">{{ m.flag }}</span>
          <span class="mk-main">
            <span class="mk-name">{{ t(`market.${m.code}`) }}</span>
            <span class="mk-bars">
              <span class="bar attr"><i :style="{ width: m.attractiveness + '%' }"></i></span>
              <span class="bar dist"><i :style="{ width: m.distance + '%' }"></i></span>
            </span>
          </span>
          <span class="mk-score">
            <span class="sc">{{ m.score.toFixed(0) }}</span>
            <span class="band" :class="m.band">{{ t(`entry.band.${m.band}`) }}</span>
          </span>
        </button>
        <p class="legend">
          <span class="sw attr"></span>{{ t('entry.legendAttr') }}
          <span class="sw dist"></span>{{ t('entry.legendDist') }}
        </p>
      </div>

      <div class="card detail" v-if="detail">
        <div class="kicker">{{ t('entry.why') }}</div>
        <h3>{{ detail.flag }} {{ t(`market.${detail.code}`) }}</h3>
        <p class="meta">{{ t('entry.frictionNote', { pct: detail.frictionPct, barrier: t(`entry.cage.${detail.topBarrier.key}`) }) }}</p>

        <div class="grid2">
          <div>
            <div class="kicker">{{ t('entry.attractiveness') }} · {{ detail.attractiveness.toFixed(0) }}</div>
            <div v-for="p in detail.parts.attractiveness" :key="p.key" class="pt">
              <span class="pt-k">{{ t(`entry.attr.${p.key}`) }}</span>
              <span class="pt-bar"><i class="attr" :style="{ width: (p.value * 100) + '%' }"></i></span>
              <span class="pt-v">+{{ p.points.toFixed(1) }}</span>
            </div>
          </div>
          <div>
            <div class="kicker">{{ t('entry.distance') }} · {{ detail.distance.toFixed(0) }}</div>
            <div v-for="p in detail.parts.distance" :key="p.key" class="pt">
              <span class="pt-k">{{ t(`entry.cage.${p.key}`) }}</span>
              <span class="pt-bar"><i class="dist" :style="{ width: (p.value * 100) + '%' }"></i></span>
              <span class="pt-v">−{{ p.points.toFixed(1) }}</span>
            </div>
          </div>
        </div>

        <div class="econ">
          <div><span class="e-l">{{ t('entry.cac') }}</span><strong>{{ money(MARKETS.find(m => m.code === detail.code).cac) }}</strong></div>
          <div><span class="e-l">{{ t('entry.arpa') }}</span><strong>{{ money(MARKETS.find(m => m.code === detail.code).arpa) }}</strong></div>
          <div>
            <span class="e-l">{{ t('entry.payback') }}</span>
            <strong :class="{ risk: detail.payback === null || detail.payback > 24 }">
              {{ detail.payback === null ? t('entry.never') : t('entry.months', { n: detail.payback }) }}
            </strong>
          </div>
        </div>
      </div>
    </div>

    <div class="card tune">
      <div class="th-row">
        <h3>{{ t('entry.tune') }}</h3>
        <p class="meta">{{ t('entry.tuneSub') }}</p>
      </div>
      <div class="sliders">
        <label v-for="k in ATTR_KEYS" :key="k" class="sl">
          <span class="sl-k">{{ t(`entry.attr.${k}`) }}</span>
          <input type="range" min="0" max="0.5" step="0.02" v-model.number="weights[k]"
            :aria-label="t('entry.weightFor', { factor: t(`entry.attr.${k}`) })" />
          <span class="sl-v">{{ weights[k].toFixed(2) }}</span>
        </label>
        <label class="sl ceil">
          <span class="sl-k">{{ t('entry.ceiling') }}</span>
          <input type="range" min="0" max="0.9" step="0.05" v-model.number="ceiling"
            :aria-label="t('entry.ceiling')" />
          <span class="sl-v">{{ (ceiling * 100).toFixed(0) }}%</span>
        </label>
      </div>
      <p class="foot">{{ t('entry.cageNote', { list: CAGE_KEYS.map(k => t(`entry.cage.${k}`)).join(' · ') }) }}</p>
    </div>
  </div>
</template>

<style scoped>
.mes { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.tn { font-size: 26px; font-weight: 800; line-height: 1; }
.tl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }
.tot { text-align: right; }

.row { display: grid; grid-template-columns: 1fr 1.1fr; gap: 16px; align-items: start; }
.list, .detail, .tune { padding: 18px 20px; }
.th-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.mk { display: grid; grid-template-columns: 26px 1fr auto; gap: 10px; align-items: center; width: 100%;
  background: transparent; border: 1px solid transparent; border-bottom: 1px dashed var(--border);
  padding: 10px 8px; cursor: pointer; color: var(--text); text-align: left; border-radius: 8px; }
.mk:hover { background: var(--surface); }
.mk.on { border-color: var(--primary); background: var(--surface); }
.mk:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.flag { font-size: 18px; }
.mk-name { display: block; font-size: 13px; font-weight: 600; margin-bottom: 5px; }
.mk-bars { display: flex; flex-direction: column; gap: 3px; }
.bar { display: block; height: 5px; border-radius: 3px; background: var(--bg-2); overflow: hidden; }
.bar i { display: block; height: 100%; border-radius: 3px; }
.bar.attr i { background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.bar.dist i { background: rgba(248, 113, 113, .65); }
.mk-score { text-align: right; }
.sc { display: block; font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; }
.band { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; padding: 1px 6px; border-radius: 4px; }
.band.enter { background: rgba(52, 211, 153, .16); color: #6ee7b7; }
.band.pilot { background: rgba(34, 211, 238, .16); color: #67e8f9; }
.band.watch { background: rgba(251, 191, 36, .16); color: #fcd34d; }
.band.defer { background: rgba(248, 113, 113, .16); color: #fca5a5; }
.legend { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-dim); margin: 12px 0 0; flex-wrap: wrap; }
.sw { width: 18px; height: 5px; border-radius: 3px; display: inline-block; }
.sw.attr { background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.sw.dist { background: rgba(248, 113, 113, .65); margin-left: 10px; }

.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin: 14px 0; }
.pt { display: grid; grid-template-columns: 84px 1fr 44px; gap: 8px; align-items: center; font-size: 11px; margin-top: 6px; }
.pt-k { color: var(--text-dim); }
.pt-bar { height: 5px; background: var(--bg-2); border-radius: 3px; overflow: hidden; }
.pt-bar i { display: block; height: 100%; }
.pt-bar i.attr { background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.pt-bar i.dist { background: rgba(248, 113, 113, .65); }
.pt-v { text-align: right; font-variant-numeric: tabular-nums; color: var(--text-dim); }

.econ { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding-top: 14px; border-top: 1px solid var(--border); }
.e-l { display: block; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 3px; }
.econ strong { font-size: 15px; font-variant-numeric: tabular-nums; }
.econ strong.risk { color: var(--danger); }

.sliders { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 20px; }
.sl { display: grid; grid-template-columns: 96px 1fr 44px; gap: 10px; align-items: center; font-size: 12px; color: var(--text-dim); }
.sl input { width: 100%; accent-color: var(--primary); }
.sl input:focus-visible { outline: 2px solid var(--primary); outline-offset: 3px; }
.sl-v { text-align: right; font-variant-numeric: tabular-nums; color: var(--text); }
.sl.ceil .sl-k { color: #fca5a5; }
.foot { font-size: 11px; color: var(--text-dim); margin: 14px 0 0; }

@media (max-width: 1024px) {
  .row { grid-template-columns: 1fr; }
  .sliders { grid-template-columns: 1fr; }
  .grid2 { grid-template-columns: 1fr; }
}
</style>
