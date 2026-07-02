<script setup>
defineProps({
  tabs: { type: Array, required: true }, /* [{v, label, count?}] */
  modelValue: { type: String, required: true }
})
defineEmits(['update:modelValue'])
</script>

<template>
  <div class="subtabs">
    <button v-for="t in tabs" :key="t.v"
      class="st" :class="{ on: modelValue === t.v }"
      @click="$emit('update:modelValue', t.v)" type="button">
      {{ t.label }}
      <span v-if="t.count !== undefined" class="cnt">{{ t.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.subtabs { display: flex; gap: 4px; padding: 4px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); width: max-content; margin-bottom: 20px; max-width: 100%; overflow-x: auto; }
.st { display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 8px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap; }
.st:hover { color: var(--text); }
.st.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }
.cnt { font-size: 11px; padding: 1px 7px; border-radius: 999px; background: rgba(0,0,0,.2); color: inherit; font-variant-numeric: tabular-nums; }
.st.on .cnt { background: rgba(255,255,255,.25); }
</style>
