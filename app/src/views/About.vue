<script setup>
import { useI18n } from 'vue-i18n'
import SectionHeader from '../components/SectionHeader.vue'
const { t } = useI18n()

const offices = [
  { city: 'Shanghai', tz: 'UTC+8', flag: '🇨🇳' },
  { city: 'Singapore', tz: 'UTC+8', flag: '🇸🇬' },
  { city: 'Tokyo', tz: 'UTC+9', flag: '🇯🇵' },
  { city: 'San Francisco', tz: 'UTC−8', flag: '🇺🇸' }
]
</script>

<template>
  <section class="section">
    <div class="container">
      <SectionHeader :title="t('about.title')" />
      <p class="lead">{{ t('about.body') }}</p>

      <div class="grid grid-3 vals">
        <div v-for="k in ['v1','v2','v3']" :key="k" class="card v">
          <h3>{{ t(`about.values.${k}.title`) }}</h3>
          <p>{{ t(`about.values.${k}.desc`) }}</p>
        </div>
      </div>

      <div class="offices">
        <h3 class="o-title">Offices</h3>
        <div class="o-grid">
          <div v-for="o in offices" :key="o.city" class="o">
            <span class="flag">{{ o.flag }}</span>
            <div>
              <div class="city">{{ o.city }}</div>
              <div class="tz">{{ o.tz }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.lead { max-width: 760px; font-size: 18px; line-height: 1.7; color: var(--text); margin: 0 0 56px; }
.vals { margin-bottom: 64px; }
.v h3 { margin-bottom: 8px; }
.v p { margin: 0; }

.offices { padding-top: 32px; border-top: 1px solid var(--border); }
.o-title { margin-bottom: 20px; }
.o-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.o { display: flex; align-items: center; gap: 14px; padding: 18px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.flag { font-size: 28px; }
.city { font-weight: 700; }
.tz { color: var(--text-dim); font-size: 13px; }
@media (max-width: 720px) { .o-grid { grid-template-columns: 1fr 1fr; } }
</style>
