<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { prefs, setConsent } from '../store/workspace.js'
import { decide } from '../logic/consent.js'

// Spec 41 — GDPR consent banner. Shows until the visitor decides; analytics
// stays off until they accept. Withdrawable later via the footer link.
const { t } = useI18n()
const show = computed(() => !prefs.consent?.decided)

function choose(choice) { setConsent(decide(choice)) }
</script>

<template>
  <div v-if="show" class="consent" role="region" :aria-label="t('consent.title')">
    <div class="c-inner">
      <div class="c-text">
        <strong>{{ t('consent.title') }}</strong>
        <span>{{ t('consent.body') }}</span>
      </div>
      <div class="c-actions">
        <button type="button" class="c-btn ghost" @click="choose('reject')">{{ t('consent.reject') }}</button>
        <button type="button" class="c-btn primary" @click="choose('accept')">{{ t('consent.accept') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.consent {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 90;
  background: rgba(10, 12, 20, .96); backdrop-filter: blur(10px);
  border-top: 1px solid var(--border);
}
.c-inner {
  max-width: 1100px; margin: 0 auto; padding: 14px 20px;
  display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap;
}
.c-text { display: flex; flex-direction: column; gap: 3px; font-size: 13px; max-width: 720px; }
.c-text span { color: var(--text-dim); }
.c-actions { display: flex; gap: 10px; flex-shrink: 0; }
.c-btn { border-radius: 9px; padding: 9px 16px; font-size: 13px; font-weight: 700; cursor: pointer; border: 1px solid var(--border); }
.c-btn.ghost { background: var(--surface); color: var(--text); }
.c-btn.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.c-btn:hover { filter: brightness(1.05); }
.c-btn:focus-visible { outline: 2px solid var(--primary-2); outline-offset: 2px; }
@media (max-width: 640px) { .c-actions { width: 100%; } .c-btn { flex: 1; } }
</style>
