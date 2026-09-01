<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { SECTIONS } from '../console/registry.js'
import { buildIndex, searchModules } from '../logic/search.js'
import { buildActionCommands } from '../logic/commands.js'
import { MOTION_PREFS } from '../logic/motion.js'
import { prefs, setMotionPref } from '../store/workspace.js'
import { locales as LOCALES, setLocale } from '../i18n'

const { t, locale } = useI18n()
const router = useRouter()

const open = ref(false)
const query = ref('')
const active = ref(0)
const inputEl = ref(null)
let lastFocused = null // element focused when the palette opened (focus return)

// Rebuild the index when the locale changes so labels match the operator's language.
const index = computed(() => {
  void locale.value
  return buildIndex(SECTIONS, (kind, path) =>
    kind === 'section' ? t(`console.s.${path}.title`) : t(`console.tabs.${path}`))
})

// Action commands (spec 39): global store-backed operations — switch language,
// set motion — searchable alongside modules. Labels rebuild with the locale.
const actionEntries = computed(() => {
  void locale.value
  return buildActionCommands({ locales: LOCALES.map(l => l.code), motionPrefs: MOTION_PREFS }).map(a => {
    const label = a.kind === 'locale'
      ? `${t('cmd.language')}: ${LOCALES.find(l => l.code === a.arg)?.label ?? a.arg}`
      : `${t('cmd.motion')}: ${t('motion.' + a.arg)}`
    return {
      id: a.id,
      label,
      sub: 'action',
      sectionLabel: t('cmd.action'),
      route: null,
      action: a,
      haystack: `${label} ${a.kind} ${a.arg} ${t('cmd.language')} ${t('cmd.motion')} command action`.toLowerCase()
    }
  })
})

// Modules first, then actions — one searchable index.
const fullIndex = computed(() => [...index.value, ...actionEntries.value])

// Recent sections (spec 32): map persisted section keys to their section-level
// index entries, dropping any key no longer in the registry.
const recents = computed(() => {
  const byId = new Map(index.value.map(e => [e.id, e]))
  return prefs.recents.map(k => byId.get(k)).filter(Boolean)
})

// Empty query → offer recents if we have any; otherwise browse the index.
const showingRecents = computed(() => !query.value.trim() && recents.value.length > 0)
const results = computed(() =>
  showingRecents.value ? recents.value : searchModules(query.value, fullIndex.value))

watch(results, () => { active.value = 0 })
watch(open, async v => {
  if (v) {
    lastFocused = typeof document !== 'undefined' ? document.activeElement : null
    query.value = ''; active.value = 0
    await nextTick(); inputEl.value?.focus()
  } else {
    // Focus return: back to wherever the user was when they opened it.
    lastFocused?.focus?.()
    lastFocused = null
  }
})

function onKey(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    open.value = !open.value
  } else if (open.value && e.key === 'Escape') {
    open.value = false
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function move(d) {
  if (!results.value.length) return
  active.value = (active.value + d + results.value.length) % results.value.length
}

function go(entry = results.value[active.value]) {
  if (!entry) return
  open.value = false
  if (entry.action) return runAction(entry.action)
  router.push(entry.route)
}

function runAction(a) {
  if (a.kind === 'locale') setLocale(a.arg)
  else if (a.kind === 'motion') setMotionPref(a.arg)
}

defineExpose({ open })
</script>

<template>
  <button class="pal-btn" type="button" @click="open = true" :aria-label="t('palette.title')" :title="t('palette.hint')">
    <span>⌘K</span>
  </button>

  <Teleport to="body">
    <div v-if="open" class="pal-back" @click.self="open = false">
      <div class="pal card" role="dialog" aria-modal="true" :aria-label="t('palette.title')">
        <input
          ref="inputEl"
          v-model="query"
          class="pal-in"
          role="combobox"
          aria-controls="pal-listbox"
          aria-expanded="true"
          :aria-activedescendant="results[active] ? 'pal-opt-' + results[active].id : undefined"
          :placeholder="t('palette.placeholder')"
          :aria-label="t('palette.placeholder')"
          @keydown.down.prevent="move(1)"
          @keydown.up.prevent="move(-1)"
          @keydown.enter.prevent="go()"
        />
        <div v-if="showingRecents" class="pal-cap">{{ t('palette.recent') }}</div>
        <ul v-if="results.length" id="pal-listbox" class="pal-list" role="listbox">
          <li
            v-for="(r, i) in results" :key="r.id"
            :id="'pal-opt-' + r.id" role="option" :aria-selected="i === active"
            class="pal-row" :class="{ on: i === active }"
            @mouseenter="active = i" @click="go(r)"
          >
            <span class="pr-label">{{ r.label }}</span>
            <span class="pr-section" v-if="r.sub">{{ r.sectionLabel }}</span>
            <span class="pr-kbd" v-if="i === active">↵</span>
          </li>
        </ul>
        <div v-else class="pal-empty">{{ t('palette.empty') }}</div>
        <div class="pal-count" role="status" aria-live="polite">{{ t('palette.count', { n: results.length }) }}</div>
        <div class="pal-foot">{{ t('palette.hint') }}</div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.pal-btn { position: fixed; right: 18px; bottom: 18px; z-index: 60; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface); color: var(--text-dim); font-size: 12px; font-weight: 700; cursor: pointer; box-shadow: 0 6px 24px rgba(0,0,0,.35); }
.pal-btn:hover { color: var(--text); border-color: rgba(124, 92, 255, .5); }

.pal-back { position: fixed; inset: 0; z-index: 70; background: rgba(8, 10, 18, .6); backdrop-filter: blur(4px); display: flex; justify-content: center; padding-top: 12vh; }
.pal { width: min(560px, 92vw); height: fit-content; padding: 10px; }
.pal-in { width: 100%; padding: 12px 14px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 15px; outline: none; }
.pal-in:focus { border-color: rgba(124, 92, 255, .55); }
.pal-list { margin: 8px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; }
.pal-count { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.pal-row { display: grid; grid-template-columns: 1fr auto auto; gap: 10px; align-items: center; text-align: left; padding: 10px 12px; border: 0; border-radius: 8px; background: transparent; color: var(--text); font-size: 13.5px; cursor: pointer; }
.pal-row.on { background: rgba(124, 92, 255, .16); }
.pr-section { font-size: 11px; color: var(--text-dim); }
.pr-kbd { font-size: 11px; color: var(--text-dim); border: 1px solid var(--border); border-radius: 5px; padding: 1px 6px; }
.pal-cap { padding: 10px 12px 2px; font-size: 10.5px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; color: var(--text-dim); }
.pal-empty { padding: 18px 12px; font-size: 13px; color: var(--text-dim); text-align: center; }
.pal-foot { margin-top: 8px; padding: 8px 12px 4px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-dim); }
</style>
