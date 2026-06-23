<script setup>
defineProps({ items: { type: Array, required: true } })
</script>
<template>
  <div class="grid grid-3">
    <div v-for="(it, i) in items" :key="i" class="card feat">
      <div class="icon" :style="{ background: it.color || 'linear-gradient(135deg, var(--primary), var(--primary-2))' }">
        <span v-html="it.icon || '✦'"></span>
      </div>
      <h3>{{ it.title }}</h3>
      <p>{{ it.desc }}</p>
    </div>
  </div>
</template>
<style scoped>
.feat { display: flex; flex-direction: column; gap: 12px; }
.icon { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; color: #fff; font-size: 20px; }
.feat h3 { margin-top: 4px; }
.feat p { margin: 0; }
</style>
