<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { analyzeFunnel } from '../logic/funnel.js'
import { useAnalytics } from '../composables/useAnalytics.js'

const { t } = useI18n()
const { recorder } = useAnalytics()

const STAGES = ['page_view', 'form_view', 'form_submit', 'form_success']

// Seeded demo baseline (the console operator hasn't necessarily hit the
// Contact form) merged additively with any live events this session.
const SEED = { page_view: 4820, form_view: 1640, form_submit: 392, form_success: 268 }

const funnel = computed(() => {
  const events = []
  for (const [name, n] of Object.entries(SEED)) for (let i = 0; i < n; i++) events.push({ name })
  events.push(...recorder.all()) // live merge
  return analyzeFunnel(events, STAGES)
})

const maxCount = computed(() => funnel.value.steps[0]?.count || 1)
const fmt = n => n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n)
const pct = r => (r * 100).toFixed(1) + '%'
</script>

<template>
  <div class="fn">
    <div class="card head">
      <div>
        <div class="kicker">{{ t('funnel.kicker') }}</div>
        <h3>{{ t('funnel.title') }}</h3>
        <p class="meta">{{ t('funnel.sub') }}</p>
      </div>
      <div class="overall">
        <div class="ov-num grad-text">{{ pct(funnel.overall) }}</div>
        <div class="ov-lbl">{{ t('funnel.overall') }}</div>
      </div>
    </div>

    <div class="card bars">
      <div v-for="(s, i) in funnel.steps" :key="s.stage" class="stage"
        :class="{ leak: funnel.biggestDrop && funnel.biggestDrop.stage === s.stage }">
        <div class="s-head">
          <span class="s-name">{{ t('funnel.stage.' + s.stage) }}</span>
          <span class="s-count">{{ fmt(s.count) }}</span>
        </div>
        <div class="track">
          <div class="fill" :style="{ width: (s.count / maxCount * 100) + '%' }"></div>
        </div>
        <div class="s-foot">
          <span v-if="i > 0" class="conv" :class="{ bad: funnel.biggestDrop && funnel.biggestDrop.stage === s.stage }">
            {{ pct(s.rate) }} {{ t('funnel.fromPrev') }}
          </span>
          <span v-else class="conv">{{ t('funnel.entry') }}</span>
        </div>
      </div>
    </div>

    <div v-if="funnel.biggestDrop" class="card leak-note">
      <span class="leak-ico">⚠️</span>
      <span>{{ t('funnel.leak', { stage: t('funnel.stage.' + funnel.biggestDrop.stage), rate: pct(funnel.biggestDrop.rate) }) }}</span>
    </div>
  </div>
</template>

<style scoped>
.fn { display: flex; flex-direction: column; gap: 14px; }
.card { padding: 18px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.head h3 { margin: 4px 0 6px; }
.meta { color: var(--text-dim); font-size: 13px; margin: 0; }
.overall { text-align: right; }
.ov-num { font-size: 34px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.ov-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.bars { display: flex; flex-direction: column; gap: 16px; }
.stage { display: flex; flex-direction: column; gap: 5px; }
.s-head { display: flex; justify-content: space-between; font-size: 13px; }
.s-name { font-weight: 600; }
.s-count { font-variant-numeric: tabular-nums; color: var(--text-dim); }
.track { height: 26px; border-radius: 8px; background: var(--surface-2); overflow: hidden; }
.fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); border-radius: 8px; transition: width .3s; }
.stage.leak .fill { background: linear-gradient(90deg, #f87171, #fbbf24); }
.s-foot { font-size: 11px; }
.conv { color: var(--text-dim); }
.conv.bad { color: #f87171; font-weight: 700; }

.leak-note { display: flex; align-items: center; gap: 10px; font-size: 13px; border-color: rgba(248, 113, 113, .3); background: rgba(248, 113, 113, .06); }
.leak-ico { font-size: 18px; }
</style>
