<script setup>
defineProps({ eyebrow: String, title: String, subtitle: String, center: { type: Boolean, default: true } })
</script>
<template>
  <header class="sh" :class="{ center }">
    <span v-if="eyebrow" class="eyebrow">{{ eyebrow }}</span>
    <h2 class="grad-text">{{ title }}</h2>
    <p v-if="subtitle">{{ subtitle }}</p>
  </header>
</template>
<style scoped>
.sh { display: flex; flex-direction: column; gap: 14px; margin-bottom: 48px; }
.sh.center { align-items: center; text-align: center; }
.sh p { max-width: 640px; margin: 0; }
</style>
