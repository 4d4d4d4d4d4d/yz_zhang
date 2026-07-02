<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { locales, setLocale } from '../i18n'

const { locale } = useI18n()
const open = ref(false)
const rootEl = ref(null)

function pick(code) {
  setLocale(code)
  open.value = false
}

function onDocClick(e) {
  if (rootEl.value && !rootEl.value.contains(e.target)) open.value = false
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div class="lang" ref="rootEl">
    <button class="lang-btn" :aria-expanded="open" @click="open = !open" type="button">
      <span class="globe" aria-hidden="true">🌐</span>
      <span>{{ locales.find(l => l.code === locale)?.label || 'EN' }}</span>
      <span class="caret" :class="{ open }">▾</span>
    </button>
    <div v-if="open" class="menu" role="listbox">
      <button
        v-for="l in locales" :key="l.code"
        class="menu-item" :class="{ active: l.code === locale }"
        @click="pick(l.code)" type="button"
      >{{ l.label }}</button>
    </div>
  </div>
</template>

<style scoped>
.lang { position: relative; }
.lang-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-radius: 999px;
  background: var(--surface); color: var(--text);
  border: 1px solid var(--border); cursor: pointer; font-size: 14px;
}
.lang-btn:hover { background: var(--surface-2); }
.globe { font-size: 14px; }
.caret { font-size: 10px; opacity: .7; transition: transform .15s; }
.caret.open { transform: rotate(180deg); }
.menu {
  position: absolute; right: 0; top: calc(100% + 6px); min-width: 160px;
  background: var(--bg-2); border: 1px solid var(--border); border-radius: 12px;
  padding: 6px; z-index: 60; box-shadow: 0 12px 32px -12px rgba(0,0,0,.6);
}
.menu-item {
  display: block; width: 100%; text-align: left; padding: 10px 12px;
  background: transparent; color: var(--text); border: none; border-radius: 8px;
  cursor: pointer; font-size: 14px;
}
.menu-item:hover { background: var(--surface-2); }
.menu-item.active { color: #fff; background: rgba(124, 92, 255, .18); }
</style>
