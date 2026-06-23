<script setup>
import { useI18n } from 'vue-i18n'
import SectionHeader from '../components/SectionHeader.vue'
import RenderStudio from '../components/RenderStudio.vue'
import NegotiationCopilot from '../components/NegotiationCopilot.vue'
const { t } = useI18n()
</script>

<template>
  <section class="section">
    <div class="container">
      <SectionHeader :eyebrow="t('nav.studio')"
        :title="t('studio.title')" :subtitle="t('studio.subtitle')" />
      <RenderStudio />
    </div>
  </section>

  <section class="section">
    <div class="container">
      <SectionHeader title="Deal Copilot"
        subtitle="An AI assistant for cross-border partnership talks — drafts, translates and pressure-tests proposals in 40+ languages." />
      <NegotiationCopilot />
    </div>
  </section>
</template>
