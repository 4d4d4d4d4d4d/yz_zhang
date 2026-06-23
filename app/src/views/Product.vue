<script setup>
import { useI18n } from 'vue-i18n'
import SectionHeader from '../components/SectionHeader.vue'
import FeatureGrid from '../components/FeatureGrid.vue'
import AIRecommend from '../components/AIRecommend.vue'
import CampaignPlanner from '../components/CampaignPlanner.vue'
import ComplianceCard from '../components/ComplianceCard.vue'
const { t } = useI18n()

const features = ['f1','f2','f3','f4','f5','f6'].map(k => ({
  title: t(`features.${k}.title`),
  desc: t(`features.${k}.desc`),
  icon: { f1:'📷', f2:'🎬', f3:'🎨', f4:'🗣️', f5:'📐', f6:'⚡' }[k]
}))
</script>

<template>
  <section class="section">
    <div class="container">
      <SectionHeader
        :eyebrow="t('hero.eyebrow')"
        :title="t('features.title')"
        :subtitle="t('features.subtitle')"
      />
      <FeatureGrid :items="features" />
    </div>
  </section>

  <section class="section">
    <div class="container">
      <SectionHeader title="AI Recommendation Engine"
        subtitle="Tell us about your product. We surface the formats, hooks and markets most likely to convert — backed by anonymized performance data from 1,200+ brands." />
      <AIRecommend />
    </div>
  </section>

  <section class="section">
    <div class="container">
      <SectionHeader title="Campaign Planner"
        subtitle="From a single brief to a fully sequenced launch plan across markets — with budget pacing and creative variants." />
      <CampaignPlanner />
    </div>
  </section>

  <section class="section">
    <div class="container">
      <SectionHeader title="Trust, risk &amp; legal — built in"
        subtitle="Brand-safe generation, content provenance and regional compliance covered out of the box." />
      <ComplianceCard />
    </div>
  </section>
</template>
