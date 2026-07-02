<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const events = ref([
  { ts: 'now',     kind: 'render',  text: 'Render completed · sneaker_v3.mp4 · 9:16 · TikTok JP' },
  { ts: '12s ago', kind: 'ai',      text: 'AI · risk review passed for DSR-2841' },
  { ts: '38s ago', kind: 'deal',    text: 'Lumen Studios viewed §4.2 redline' },
  { ts: '1m ago',  kind: 'partner', text: 'Mizu Logistics submitted KYB bank docs' },
  { ts: '2m ago',  kind: 'campaign',text: 'TikTok · Lumi JP · ROAS crossed 4.5×' }
])

const templates = [
  { kind: 'render',  texts: ['Render completed · {brand}_{v}.mp4', 'Rendering started · {brand} · {format}', 'C2PA signed · 24 outputs'] },
  { kind: 'ai',      texts: ['AI agent · {agent} flagged a risk on §{n}', 'Bandit · arm {a} promoted to {p}% traffic', 'Model drift on {cohort} cohort = {d}%'] },
  { kind: 'deal',    texts: ['{partner} accepted §{n}', '{partner} requested redline on §{n}', '{signer} signed MSA v{v}'] },
  { kind: 'partner', texts: ['{partner} submitted {doc}', 'New partner intro from {via}', '{partner} replied within {t}'] },
  { kind: 'campaign',texts: ['{channel} · {campaign} · ROAS {r}×', 'Budget moved {delta} → {channel}', 'Audience {seg} pushed to ad accounts'] },
  { kind: 'security', texts: ['SSO session refreshed for {user}', 'KMS key rotated · {region}', 'p95 latency dropped to {ms}ms'] }
]
const brands = ['lumi', 'kaito', 'sneaker', 'apparel', 'gadget']
const partners = ['Lumen', 'Aurora', 'Mizu', 'Cobalt', 'Northwave', 'Helio']
const channels = ['TikTok', 'Meta', 'Google', 'YouTube']
const agents = ['Vision', 'Compliance', 'Margin', 'Precedent']
const docs = ['bank docs', 'address proof', 'DPA', 'NDA']

function pick(arr) { return arr[Math.floor(Math.random() * arr.length)] }
function fill(t) {
  return t
    .replace('{brand}', pick(brands))
    .replace('{v}', 'v' + (Math.floor(Math.random() * 5) + 1))
    .replace('{format}', pick(['9:16', '1:1', '16:9', '6s']))
    .replace('{agent}', pick(agents))
    .replace('{n}', String(Math.floor(Math.random() * 8) + 1) + '.' + (Math.floor(Math.random() * 5) + 1))
    .replace('{a}', pick(['A', 'B', 'C', 'D']))
    .replace('{p}', String(Math.floor(Math.random() * 60) + 20))
    .replace('{cohort}', pick(['US', 'JP', 'KR', 'BR']))
    .replace('{d}', String(Math.floor(Math.random() * 10) + 2))
    .replace('{partner}', pick(partners))
    .replace('{signer}', pick(['CEO', 'COO', 'GC']))
    .replace('{doc}', pick(docs))
    .replace('{via}', pick(partners) + '\'s team')
    .replace('{t}', Math.floor(Math.random() * 60) + 1 + 'h')
    .replace('{channel}', pick(channels))
    .replace('{campaign}', pick(brands) + ' · ' + pick(['JP', 'US', 'BR', 'KR']))
    .replace('{r}', (2 + Math.random() * 3).toFixed(1))
    .replace('{delta}', '+' + (Math.floor(Math.random() * 20) + 5) + '%')
    .replace('{seg}', pick(['Gen Z JP', 'KR beauty', 'BR moms', 'US lapsed']))
    .replace('{user}', pick(['amori', 'ktanaka', 'hyamazaki']))
    .replace('{region}', pick(['ap-northeast-1', 'eu-west-1', 'us-west-2']))
    .replace('{ms}', String(Math.floor(Math.random() * 40) + 60))
}

let timer
onMounted(() => {
  timer = setInterval(() => {
    const tpl = pick(templates)
    const text = fill(pick(tpl.texts))
    events.value.unshift({ ts: 'now', kind: tpl.kind, text })
    for (let i = 1; i < events.value.length; i++) {
      const e = events.value[i]
      if (e.ts === 'now') e.ts = '8s ago'
      else if (e.ts.endsWith('s ago')) {
        const n = parseInt(e.ts) + 8
        e.ts = n > 60 ? Math.floor(n / 60) + 'm ago' : n + 's ago'
      }
    }
    if (events.value.length > 12) events.value.pop()
  }, 2200)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="feed card">
    <div class="head">
      <div class="hl">
        <span class="dot"></span>
        <h3>Live activity</h3>
      </div>
      <span class="meta">Streaming · 5 sources</span>
    </div>
    <transition-group name="evt" tag="div" class="list">
      <div v-for="e in events" :key="e.ts + e.text" class="evt" :class="e.kind">
        <span class="ico">{{
          { render: '🎬', ai: '🤖', deal: '📝', partner: '🤝', campaign: '📈', security: '🛡' }[e.kind]
        }}</span>
        <span class="text">{{ e.text }}</span>
        <span class="ts">{{ e.ts }}</span>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.feed { padding: 16px 18px; margin-top: 20px; }
.head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; }
.hl { display: flex; align-items: center; gap: 10px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 10px var(--success); animation: pl 1.4s ease-in-out infinite; }
@keyframes pl { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
.meta { color: var(--text-dim); font-size: 12px; }

.list { display: flex; flex-direction: column; gap: 4px; max-height: 220px; overflow-y: auto; }
.evt { display: grid; grid-template-columns: 24px 1fr auto; gap: 10px; align-items: center; padding: 6px 8px; border-radius: 6px; font-size: 13px; transition: background .15s; }
.evt:hover { background: var(--surface); }
.ico { font-size: 14px; }
.text { color: var(--text); }
.evt.ai .text { color: var(--primary-2); }
.evt.deal .text { color: #f5d0fe; }
.evt.partner .text { color: #93c5fd; }
.evt.campaign .text { color: #fcd34d; }
.evt.security .text { color: #6ee7b7; }
.ts { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; }

.evt-enter-active { transition: all .35s ease; }
.evt-enter-from { opacity: 0; transform: translateY(-6px); background: rgba(124, 92, 255, .15); }
.evt-leave-active { transition: opacity .2s ease; }
.evt-leave-to { opacity: 0; }
</style>
