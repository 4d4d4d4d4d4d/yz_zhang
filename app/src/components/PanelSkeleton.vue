<script setup>
import { useI18n } from 'vue-i18n'

// Spec 59 — shown only when a section chunk takes longer than 180ms. It is an
// aria-busy region rather than a spinner so a screen reader announces that the
// module is arriving instead of silently reading a blank card.
const { t } = useI18n()
</script>

<template>
  <div class="sk card" role="status" aria-busy="true" :aria-label="t('console.loading')">
    <div class="sk-bar w60"></div>
    <div class="sk-bar w40"></div>
    <div class="sk-grid">
      <div v-for="i in 4" :key="i" class="sk-tile"></div>
    </div>
    <span class="sr-only">{{ t('console.loading') }}</span>
  </div>
</template>

<style scoped>
.sk { padding: 20px; display: flex; flex-direction: column; gap: 12px; }
.sk-bar, .sk-tile { border-radius: 8px; background: var(--surface); position: relative; overflow: hidden; }
.sk-bar { height: 14px; }
.w60 { width: 60%; }
.w40 { width: 40%; }
.sk-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 6px; }
.sk-tile { height: 78px; }
.sk-bar::after, .sk-tile::after {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .06), transparent);
  transform: translateX(-100%); animation: sheen 1.2s infinite;
}
@keyframes sheen { to { transform: translateX(100%); } }
@media (prefers-reduced-motion: reduce) {
  .sk-bar::after, .sk-tile::after { animation: none; }
}
@media (max-width: 720px) { .sk-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
