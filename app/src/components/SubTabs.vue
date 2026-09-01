<script setup>
import { ref } from 'vue'

const props = defineProps({
  tabs: { type: Array, required: true }, /* [{v, label, count?}] */
  modelValue: { type: String, required: true }
})
const emit = defineEmits(['update:modelValue'])

const btns = ref([])

// Spec 31 — WAI-ARIA Tabs pattern, automatic activation (move = select).
function selectAt(i) {
  const wrapped = (i + props.tabs.length) % props.tabs.length
  const tab = props.tabs[wrapped]
  emit('update:modelValue', tab.v)
  btns.value[wrapped]?.focus()
}

function onKey(e, idx) {
  switch (e.key) {
    case 'ArrowRight': case 'ArrowDown': e.preventDefault(); selectAt(idx + 1); break
    case 'ArrowLeft':  case 'ArrowUp':   e.preventDefault(); selectAt(idx - 1); break
    case 'Home': e.preventDefault(); selectAt(0); break
    case 'End':  e.preventDefault(); selectAt(props.tabs.length - 1); break
  }
}
</script>

<template>
  <div class="subtabs" role="tablist">
    <button v-for="(t, i) in tabs" :key="t.v" ref="btns"
      class="st" :class="{ on: modelValue === t.v }"
      role="tab" :aria-selected="modelValue === t.v"
      :tabindex="modelValue === t.v ? 0 : -1"
      @click="$emit('update:modelValue', t.v)"
      @keydown="onKey($event, i)" type="button">
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
