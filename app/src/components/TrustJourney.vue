<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// Spec 23 — pure presentation: copy from product.journey.*, links into
// the live console demos. No logic module (and none needed).
const STEPS = [
  { key: 's1', icon: '🎬', hue: 262, to: { name: 'console', params: { tab: 'showcase' } } },
  { key: 's2', icon: '🕶', hue: 190, to: { name: 'console', params: { tab: 'immersive' } } },
  { key: 's3', icon: '🔍', hue: 152, to: { name: 'console', params: { tab: 'immersive' } } },
  { key: 's4', icon: '✍️', hue: 28,  to: { name: 'console', params: { tab: 'showcase' } } }
]
</script>

<template>
  <div class="tj">
    <div class="steps">
      <router-link v-for="(s, i) in STEPS" :key="s.key" :to="s.to" class="step card" :style="{ '--h': s.hue }">
        <div class="s-top">
          <span class="n">{{ i + 1 }}</span>
          <span class="ico">{{ s.icon }}</span>
        </div>
        <h3>{{ t(`product.journey.${s.key}.title`) }}</h3>
        <p>{{ t(`product.journey.${s.key}.desc`) }}</p>
        <span class="go">{{ t('product.journey.cta') }} →</span>
      </router-link>
    </div>
    <p class="note">{{ t('product.journey.note') }}</p>
  </div>
</template>

<style scoped>
.tj { display: flex; flex-direction: column; gap: 14px; }
.steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.step { padding: 20px 18px; display: flex; flex-direction: column; gap: 8px; color: var(--text); transition: transform .15s, border-color .15s; position: relative; overflow: hidden; }
.step::before { content: ''; position: absolute; inset: 0 0 auto; height: 3px; background: hsl(var(--h) 75% 60%); }
.step:hover { transform: translateY(-3px); border-color: hsl(var(--h) 70% 55% / .5); }
.s-top { display: flex; justify-content: space-between; align-items: center; }
.n { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-size: 12px; font-weight: 800; background: hsl(var(--h) 70% 55% / .18); color: hsl(var(--h) 80% 70%); }
.ico { font-size: 20px; }
.step h3 { margin: 4px 0 0; font-size: 16px; }
.step p { margin: 0; font-size: 12.5px; color: var(--text-dim); line-height: 1.55; flex: 1; }
.go { font-size: 11px; font-weight: 700; color: hsl(var(--h) 80% 70%); text-transform: uppercase; letter-spacing: .06em; }
.note { margin: 0; text-align: center; font-size: 12px; color: var(--text-dim); }
@media (max-width: 900px) { .steps { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .steps { grid-template-columns: 1fr; } }
</style>
