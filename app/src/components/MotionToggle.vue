<script setup>
import { useI18n } from 'vue-i18n'
import { useReducedMotion } from '../composables/useReducedMotion.js'
import { nextMotionPref } from '../logic/motion.js'

// Spec 38 — a single control that cycles the motion preference
// (system → reduce → full). Beyond the OS setting, per GitHub/Slack.
const { t } = useI18n()
const { motionPref, setMotionPref } = useReducedMotion()

const ICON = { system: '🖥', reduce: '⏸', full: '🎞' }
function cycle() { setMotionPref(nextMotionPref(motionPref.value)) }
</script>

<template>
  <button
    class="motion-btn" type="button" @click="cycle"
    :aria-label="t('motion.label') + ': ' + t('motion.' + motionPref)"
    :title="t('motion.label') + ': ' + t('motion.' + motionPref)"
  >
    <span aria-hidden="true">{{ ICON[motionPref] }}</span>
    <span class="mb-lbl">{{ t('motion.' + motionPref) }}</span>
  </button>
</template>

<style scoped>
.motion-btn {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--surface); border: 1px solid var(--border); color: var(--text-dim);
  border-radius: 9px; padding: 7px 10px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.motion-btn:hover { color: var(--text); border-color: rgba(124, 92, 255, .5); }
.motion-btn:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.mb-lbl { text-transform: capitalize; }
@media (max-width: 900px) { .mb-lbl { display: inline; } }
</style>
