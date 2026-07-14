<script setup>
import { ref, onErrorCaptured } from 'vue'
import { useI18n } from 'vue-i18n'

// Spec 27 — module-level error boundary: one broken module renders a
// localized fallback card instead of blanking the whole console.
const { t } = useI18n()
const error = ref(null)

onErrorCaptured(err => {
  error.value = err
  return false // stop propagation — the shell stays alive
})

function retry() { error.value = null }
defineExpose({ error })
</script>

<template>
  <div v-if="error" class="boundary card">
    <div class="b-ico">⚠️</div>
    <h3>{{ t('boundary.title') }}</h3>
    <p class="b-msg">{{ error.message }}</p>
    <button class="btn btn-ghost sm" type="button" @click="retry">{{ t('boundary.retry') }}</button>
  </div>
  <slot v-else />
</template>

<style scoped>
.boundary { padding: 40px 24px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8px; border-color: rgba(248, 113, 113, .35); }
.b-ico { font-size: 28px; }
.boundary h3 { margin: 0; }
.b-msg { margin: 0 0 10px; font-size: 12px; color: var(--text-dim); font-family: ui-monospace, monospace; max-width: 480px; }
.btn.sm { padding: 7px 16px; font-size: 12px; }
</style>
