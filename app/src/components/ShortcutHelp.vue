<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { shortcutRows } from '../logic/shortcuts.js'

// Spec 32 — the `?` keyboard cheat-sheet. Rows are generated from the live
// GOTO_MAP so the sheet can never drift; labels are resolved here via i18n.
const { t } = useI18n()
const open = ref(false)
const dialogEl = ref(null)
let lastFocused = null

const rows = shortcutRows()

// Localized label for a goto row (route → registry/i18n title).
function gotoLabel(route) {
  return route.name === 'home' ? t('nav.home') : t(`console.s.${route.params.tab}.title`)
}
const globalLabels = { palette: 'palette', help: 'help', tabs: 'tabs' }
function globalLabel(id) { return t(`shortcuts.${globalLabels[id]}`) }

const goto = computed(() => rows.goto.map(r => ({ keys: r.keys, label: gotoLabel(r.route) })))

function isTyping(el) {
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

function onKey(e) {
  // `?` is Shift + / on most layouts — accept either the resolved char or the combo.
  if (!open.value && e.key === '?' && !e.metaKey && !e.ctrlKey && !e.altKey && !isTyping(e.target)) {
    e.preventDefault(); open.value = true; return
  }
  if (!open.value) return
  if (e.key === 'Escape') { e.preventDefault(); open.value = false; return }
  if (e.key === 'Tab') trapFocus(e)
}

// Minimal focus trap: only the close button is focusable, so keep focus on it.
function trapFocus(e) {
  e.preventDefault()
  dialogEl.value?.querySelector('.sh-close')?.focus()
}

watch(open, async v => {
  if (v) {
    lastFocused = typeof document !== 'undefined' ? document.activeElement : null
    await nextTick()
    dialogEl.value?.querySelector('.sh-close')?.focus()
  } else {
    lastFocused?.focus?.()
    lastFocused = null
  }
})

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="sh-back" @click.self="open = false">
      <div ref="dialogEl" class="sh card" role="dialog" aria-modal="true" :aria-label="t('shortcuts.title')">
        <div class="sh-head">
          <h2 class="sh-title">{{ t('shortcuts.title') }}</h2>
          <button class="sh-close" type="button" :aria-label="t('shortcuts.close')" @click="open = false">✕</button>
        </div>

        <div class="sh-group">
          <div class="sh-cap">{{ t('shortcuts.global') }}</div>
          <div v-for="r in rows.global" :key="r.id" class="sh-row">
            <span class="sh-label">{{ globalLabel(r.id) }}</span>
            <span class="sh-keys"><kbd v-for="(k, i) in r.keys" :key="i">{{ k }}</kbd></span>
          </div>
        </div>

        <div class="sh-group">
          <div class="sh-cap">{{ t('shortcuts.jump') }}</div>
          <div v-for="(r, i) in goto" :key="i" class="sh-row">
            <span class="sh-label">{{ r.label }}</span>
            <span class="sh-keys"><kbd v-for="(k, j) in r.keys" :key="j">{{ k }}</kbd></span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.sh-back { position: fixed; inset: 0; z-index: 80; background: rgba(8, 10, 18, .6); backdrop-filter: blur(4px); display: flex; justify-content: center; padding-top: 10vh; }
.sh { width: min(460px, 92vw); height: fit-content; padding: 16px 18px; }
.sh-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.sh-title { margin: 0; font-size: 15px; }
.sh-close { border: 1px solid var(--border); background: var(--surface); color: var(--text-dim); border-radius: 8px; width: 30px; height: 30px; cursor: pointer; font-size: 13px; }
.sh-close:hover, .sh-close:focus-visible { color: var(--text); border-color: rgba(124, 92, 255, .55); outline: none; }
.sh-group { margin-top: 12px; }
.sh-cap { font-size: 10.5px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 4px; }
.sh-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 4px; border-bottom: 1px solid rgba(255,255,255,.04); font-size: 13px; }
.sh-label { color: var(--text); }
.sh-keys { display: inline-flex; gap: 4px; }
kbd { font-family: inherit; font-size: 11px; min-width: 20px; text-align: center; color: var(--text-dim); background: var(--surface); border: 1px solid var(--border); border-radius: 5px; padding: 2px 6px; }
</style>
