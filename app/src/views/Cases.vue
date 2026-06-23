<script setup>
import { useI18n } from 'vue-i18n'
import SectionHeader from '../components/SectionHeader.vue'
import LogoCloud from '../components/LogoCloud.vue'
const { t } = useI18n()
const keys = ['c1', 'c2', 'c3']
const accents = [
  'linear-gradient(135deg,#7c5cff,#22d3ee)',
  'linear-gradient(135deg,#ff7ad9,#7c5cff)',
  'linear-gradient(135deg,#22d3ee,#34d399)'
]
</script>

<template>
  <section class="section">
    <div class="container">
      <SectionHeader :eyebrow="t('nav.cases')"
        :title="t('cases.title')" :subtitle="t('cases.subtitle')" />
      <div class="grid grid-3">
        <article v-for="(k, i) in keys" :key="k" class="card case">
          <div class="case-hero" :style="{ background: accents[i] }">
            <span class="case-brand">{{ t(`cases.${k}.brand`) }}</span>
          </div>
          <div class="case-body">
            <div class="case-meta">{{ t(`cases.${k}.region`) }}</div>
            <div class="case-metric grad-text">{{ t(`cases.${k}.metric`) }}</div>
            <blockquote>“{{ t(`cases.${k}.quote`) }}”</blockquote>
          </div>
        </article>
      </div>

      <div style="margin-top: 64px;">
        <LogoCloud />
      </div>
    </div>
  </section>
</template>

<style scoped>
.case { padding: 0; overflow: hidden; display: flex; flex-direction: column; }
.case-hero { aspect-ratio: 16 / 9; display: grid; place-items: center; }
.case-brand { color: #fff; font-weight: 800; font-size: 28px; letter-spacing: -0.02em; text-shadow: 0 8px 24px rgba(0,0,0,.35); }
.case-body { padding: 24px; }
.case-meta { font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 8px; }
.case-metric { font-size: 28px; font-weight: 800; margin-bottom: 12px; }
blockquote { margin: 0; color: var(--text); font-style: italic; line-height: 1.55; }
</style>
