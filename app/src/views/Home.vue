<script setup>
import { useI18n } from 'vue-i18n'
import VideoHero from '../components/VideoHero.vue'
import SectionHeader from '../components/SectionHeader.vue'
import FeatureGrid from '../components/FeatureGrid.vue'
import StatStrip from '../components/StatStrip.vue'
import LogoCloud from '../components/LogoCloud.vue'

const { t } = useI18n()

const features = [
  { key: 'f1', icon: '📷', color: 'linear-gradient(135deg,#7c5cff,#22d3ee)' },
  { key: 'f2', icon: '🎬', color: 'linear-gradient(135deg,#ff7ad9,#7c5cff)' },
  { key: 'f3', icon: '🎨', color: 'linear-gradient(135deg,#22d3ee,#34d399)' },
  { key: 'f4', icon: '🗣️', color: 'linear-gradient(135deg,#fbbf24,#ff7ad9)' },
  { key: 'f5', icon: '📐', color: 'linear-gradient(135deg,#60a5fa,#7c5cff)' },
  { key: 'f6', icon: '⚡', color: 'linear-gradient(135deg,#34d399,#22d3ee)' }
]
</script>

<template>
  <section class="hero">
    <div class="container hero-inner">
      <div class="hero-text">
        <span class="eyebrow">{{ t('hero.eyebrow') }}</span>
        <h1 class="grad-text">{{ t('hero.title') }}</h1>
        <p>{{ t('hero.subtitle') }}</p>
        <div class="hero-cta">
          <router-link to="/studio" class="btn btn-primary">{{ t('cta.primary') }} →</router-link>
          <router-link to="/product" class="btn btn-ghost">▶ {{ t('cta.secondary') }}</router-link>
        </div>
      </div>
      <div class="hero-visual">
        <VideoHero />
      </div>
    </div>
  </section>

  <section class="section--tight">
    <div class="container">
      <StatStrip :stats="[
        { num: '1,200+', label: t('hero.stat1') },
        { num: '−72%', label: t('hero.stat2') },
        { num: '40+', label: t('hero.stat3') }
      ]" />
    </div>
  </section>

  <section class="section--tight">
    <div class="container">
      <div class="trust-line">{{ t('trust.title') }}</div>
      <LogoCloud />
    </div>
  </section>

  <section class="section">
    <div class="container">
      <SectionHeader :title="t('features.title')" :subtitle="t('features.subtitle')" />
      <FeatureGrid :items="features.map(f => ({
        title: t(`features.${f.key}.title`),
        desc: t(`features.${f.key}.desc`),
        icon: f.icon,
        color: f.color
      }))" />
    </div>
  </section>

  <section class="section how">
    <div class="container">
      <SectionHeader :title="t('how.title')" />
      <div class="steps">
        <div class="step" v-for="(k, i) in ['s1','s2','s3']" :key="k">
          <div class="step-num">{{ String(i + 1).padStart(2, '0') }}</div>
          <h3>{{ t(`how.${k}.title`) }}</h3>
          <p>{{ t(`how.${k}.desc`) }}</p>
        </div>
      </div>
    </div>
  </section>

  <section class="section cta-band">
    <div class="container cta-inner">
      <div>
        <h2 class="grad-text">{{ t('contact.title') }}</h2>
        <p>{{ t('contact.subtitle') }}</p>
      </div>
      <div class="cta-actions">
        <router-link to="/contact" class="btn btn-primary">{{ t('cta.contact') }} →</router-link>
        <router-link to="/studio" class="btn btn-ghost">{{ t('nav.studio') }}</router-link>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero { padding: 72px 0 48px; }
.hero-inner {
  display: grid; grid-template-columns: 1.05fr 1fr; gap: 56px; align-items: center;
}
.hero-text { display: flex; flex-direction: column; gap: 20px; }
.hero-text p { font-size: 18px; max-width: 540px; }
.hero-cta { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; }

.trust-line { text-align: center; color: var(--text-dim); font-size: 13px; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 24px; }

.steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.step { padding: 28px; border: 1px solid var(--border); border-radius: var(--radius); background: rgba(20,20,31,.4); position: relative; }
.step-num { font-size: 13px; color: var(--primary-2); font-weight: 700; letter-spacing: .15em; margin-bottom: 12px; }
.step h3 { margin-bottom: 8px; }
.step p { margin: 0; }

.cta-band { padding: 56px 0; }
.cta-inner {
  display: grid; grid-template-columns: 2fr 1fr; gap: 32px; align-items: center;
  padding: 40px; border: 1px solid var(--border); border-radius: 22px;
  background: linear-gradient(135deg, rgba(124,92,255,.18), rgba(34,211,238,.06));
}
.cta-inner p { margin: 8px 0 0; }
.cta-actions { display: flex; flex-direction: column; gap: 10px; }
.cta-actions :deep(.btn) { justify-content: center; }

@media (max-width: 900px) {
  .hero-inner { grid-template-columns: 1fr; }
  .steps { grid-template-columns: 1fr; }
  .cta-inner { grid-template-columns: 1fr; }
}
</style>
