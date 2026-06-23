<script setup>
defineProps({ stats: { type: Array, required: true } })
</script>
<template>
  <div class="stats">
    <div v-for="(s, i) in stats" :key="i" class="stat">
      <div class="num grad-text">{{ s.num }}</div>
      <div class="lbl">{{ s.label }}</div>
    </div>
  </div>
</template>
<style scoped>
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; padding: 28px; border: 1px solid var(--border); border-radius: var(--radius); background: rgba(20, 20, 31, .4); }
.stat { text-align: center; }
.num { font-size: clamp(28px, 3.5vw, 42px); font-weight: 800; }
.lbl { color: var(--text-dim); font-size: 14px; margin-top: 4px; }
@media (max-width: 720px) { .stats { grid-template-columns: 1fr; } }
</style>
