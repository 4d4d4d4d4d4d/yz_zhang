<script setup>
const logos = ['Lumi', 'Northwave', 'Kaito', 'Aurora', 'Cobalt', 'Helio', 'Mizu', 'Verda']
</script>
<template>
  <div class="cloud">
    <div v-for="l in logos" :key="l" class="logo">{{ l }}</div>
  </div>
</template>
<style scoped>
.cloud {
  display: grid; grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 16px; align-items: center;
}
.logo {
  text-align: center; color: var(--text-dim); font-weight: 700; letter-spacing: .04em;
  padding: 14px 0; border: 1px solid var(--border); border-radius: 10px;
  background: rgba(20, 20, 31, .35); font-size: 14px;
}
@media (max-width: 900px) { .cloud { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 480px) { .cloud { grid-template-columns: repeat(2, 1fr); } }
</style>
