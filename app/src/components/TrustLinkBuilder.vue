<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { createTrustLink, validateTrustLink, revokeTrustLink, MAX_LINK_DAYS } from '../logic/showcase.js'

const REELS = [
  { id: 'r1', title: 'Lumi Serum — Tokyo Launch' },
  { id: 'r2', title: 'Northwave — LATAM Signup' },
  { id: 'r3', title: 'Kaito Beauty — SEA UGC Wave' },
  { id: 'r6', title: 'Aria Audio — KR Before/After' }
]
const SCOPES = [
  { id: 'assets',     label: 'Video assets',        note: 'Watch the reels (watermarked)' },
  { id: 'metrics',    label: 'Verified metrics',    note: 'Platform-API performance numbers' },
  { id: 'provenance', label: 'Content credentials', note: 'C2PA chain & signing details' },
  { id: 'pricing',    label: 'Pricing',             note: 'Off by default — least privilege' }
]

const selReels = ref(['r1', 'r3'])
const selScopes = ref(['assets', 'metrics', 'provenance'])
const days = ref(7)
const watermark = ref(true)
const error = ref('')
const links = ref([])
const nowTick = ref(Date.now())
let timer
onMounted(() => { timer = setInterval(() => { nowTick.value = Date.now() }, 5000) })
onBeforeUnmount(() => clearInterval(timer))

function toggle(list, id) {
  const i = list.indexOf(id)
  i >= 0 ? list.splice(i, 1) : list.push(id)
}

function create() {
  error.value = ''
  if (!selReels.value.length) { error.value = 'Select at least one reel to share.'; return }
  try {
    const link = createTrustLink({
      reelIds: [...selReels.value],
      scopes: [...selScopes.value],
      expiresInDays: days.value,
      watermark: watermark.value
    })
    links.value.unshift(link)
  } catch (e) {
    error.value = e.message
  }
}

function statusOf(link) {
  const v = validateTrustLink(link, nowTick.value)
  return v.valid ? 'active' : v.reason
}

const daysClamped = computed(() => Math.min(MAX_LINK_DAYS, Math.max(1, days.value || 1)))
const fmtDate = ts => new Date(ts).toISOString().slice(0, 10)
</script>

<template>
  <div class="tlb">
    <div class="card head">
      <div class="kicker">Trust links · least-privilege sharing</div>
      <h3>Share proof, keep control</h3>
      <p class="meta">Scoped, expiring, watermarked links to your verified showcase. Tokens are opaque — nothing is decodable client-side. Raw assets never leave without a watermark.</p>
    </div>

    <div class="grid">
      <div class="card form">
        <div class="f-sec">
          <div class="kicker">Reels to include</div>
          <button v-for="r in REELS" :key="r.id" type="button"
            class="chip" :class="{ on: selReels.includes(r.id) }" @click="toggle(selReels, r.id)">
            {{ r.title }}
          </button>
        </div>

        <div class="f-sec">
          <div class="kicker">Scopes</div>
          <label v-for="s in SCOPES" :key="s.id" class="scope">
            <input type="checkbox" :checked="selScopes.includes(s.id)" @change="toggle(selScopes, s.id)" />
            <span><strong>{{ s.label }}</strong><em>{{ s.note }}</em></span>
          </label>
        </div>

        <div class="f-sec row">
          <label class="num">Expires in
            <input type="number" v-model.number="days" min="1" :max="MAX_LINK_DAYS" /> days
            <em v-if="days !== daysClamped">→ clamped to {{ daysClamped }}</em>
          </label>
          <label class="scope wm">
            <input type="checkbox" v-model="watermark" />
            <span><strong>Watermark</strong><em>Required whenever assets are shared</em></span>
          </label>
        </div>

        <p v-if="error" class="err">⚠ {{ error }}</p>
        <button class="btn btn-primary" type="button" @click="create">Create trust link</button>
      </div>

      <div class="card list">
        <h3>Issued links · {{ links.length }}</h3>
        <p v-if="!links.length" class="meta">No links yet — create one to see the audit trail here.</p>
        <div v-for="l in links" :key="l.token" class="link" :class="statusOf(l)">
          <div class="l-top">
            <code>adforge.ai/t/{{ l.token.slice(0, 10) }}…</code>
            <span class="st">{{ statusOf(l) }}</span>
          </div>
          <div class="l-meta">
            <span>{{ l.reelIds.length }} reels</span>
            <span>{{ l.scopes.join(' · ') || 'no scopes' }}</span>
            <span>{{ l.watermark ? 'watermarked' : 'no watermark' }}</span>
            <span>expires {{ fmtDate(l.expiresAt) }}</span>
          </div>
          <button v-if="!l.revoked" class="btn btn-ghost sm" type="button" @click="revokeTrustLink(l)">Revoke</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tlb { display: flex; flex-direction: column; gap: 16px; }
.card { padding: 18px; }
.head h3 { margin: 4px 0 6px; }
.meta { color: var(--text-dim); font-size: 13px; margin: 0; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 8px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: start; }

.f-sec { margin-bottom: 16px; }
.f-sec.row { display: flex; gap: 18px; align-items: flex-start; flex-wrap: wrap; }
.chip { display: inline-block; margin: 0 6px 6px 0; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text-dim); font-size: 12px; cursor: pointer; }
.chip.on { border-color: rgba(124, 92, 255, .5); background: rgba(124, 92, 255, .15); color: #fff; }
.scope { display: grid; grid-template-columns: 16px 1fr; gap: 10px; align-items: start; padding: 6px 0; cursor: pointer; }
.scope span { display: flex; flex-direction: column; font-size: 12px; }
.scope em { font-style: normal; color: var(--text-dim); font-size: 11px; }
.num { font-size: 12px; color: var(--text-dim); display: flex; align-items: center; gap: 8px; }
.num input { width: 64px; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text); }
.num em { font-style: normal; color: #fbbf24; font-size: 11px; }
.err { color: #f87171; font-size: 12px; margin: 0 0 12px; }

.list h3 { margin: 0 0 10px; }
.link { border: 1px solid var(--border); border-radius: 12px; padding: 12px; margin-bottom: 10px; }
.link.expired, .link.revoked { opacity: .55; }
.l-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.l-top code { font-size: 12px; }
.st { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; padding: 2px 8px; border-radius: 999px; background: rgba(52, 211, 153, .15); color: #34d399; }
.link.revoked .st, .link.expired .st { background: rgba(248, 113, 113, .15); color: #f87171; }
.l-meta { display: flex; flex-wrap: wrap; gap: 10px; margin: 8px 0 10px; font-size: 11px; color: var(--text-dim); }
.btn.sm { padding: 5px 12px; font-size: 11px; }

@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
</style>
