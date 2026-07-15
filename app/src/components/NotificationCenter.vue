<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useInbox } from '../store/workspace.js'

const { t } = useI18n()
const router = useRouter()

// Spec 27: the inbox is a shared, persisted store — the bell shows the
// same facts as the module pages, and read-state survives reloads.
const { items, unread, markRead, markAllRead } = useInbox()

const open = ref(false)
const bellEl = ref(null)
const DOT = { critical: '#f87171', warning: '#fbbf24', info: '#22d3ee' }

function close() { open.value = false; bellEl.value?.focus?.() } // focus return

function go(item) {
  markRead(item.key)
  open.value = false
  router.push(item.route)
}
</script>

<template>
  <div class="nc" @keydown.esc="open && close()">
    <button ref="bellEl" class="bell" type="button" @click="open = !open"
      :aria-label="t('notify.aria', { n: unread })" :aria-expanded="open" :title="t('notify.title')">
      🔔<span v-if="unread" class="badge">{{ unread }}</span>
    </button>

    <div v-if="open" class="panel card" role="dialog" :aria-label="t('notify.title')">
      <div class="p-head">
        <strong>{{ t('notify.title') }}</strong>
        <button v-if="unread" class="mark" type="button" @click="markAllRead">{{ t('notify.markAll') }}</button>
      </div>
      <div v-if="!items.length" class="empty">{{ t('notify.empty') }}</div>
      <button v-for="i in items" :key="i.key" type="button" class="row" :class="{ read: i.read }" @click="go(i)">
        <span class="dot" :style="{ background: DOT[i.severity] }"></span>
        <span class="msg">{{ t(i.msgKey, i.params) }}</span>
        <span class="go">→</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.nc { position: relative; }
.bell { position: relative; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface); cursor: pointer; font-size: 15px; }
.bell:hover { border-color: rgba(124, 92, 255, .5); }
.badge { position: absolute; top: -6px; right: -6px; min-width: 18px; height: 18px; border-radius: 999px; background: #f87171; color: #fff; font-size: 10px; font-weight: 800; display: grid; place-items: center; padding: 0 4px; }

.panel { position: absolute; right: 0; top: 44px; width: min(400px, 88vw); z-index: 50; padding: 12px; }
.p-head { display: flex; justify-content: space-between; align-items: center; padding: 2px 4px 10px; font-size: 13px; }
.mark { border: 0; background: transparent; color: var(--primary); font-size: 11px; cursor: pointer; }
.empty { padding: 16px 4px; font-size: 12px; color: var(--text-dim); text-align: center; }
.row { display: grid; grid-template-columns: 10px 1fr auto; gap: 10px; align-items: center; width: 100%; text-align: left; padding: 10px 8px; border: 0; border-radius: 8px; background: transparent; color: var(--text); font-size: 12.5px; cursor: pointer; line-height: 1.45; }
.row:hover { background: rgba(124, 92, 255, .1); }
.row.read { opacity: .55; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.go { color: var(--text-dim); font-size: 12px; }
</style>
