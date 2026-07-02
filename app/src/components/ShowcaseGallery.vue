<script setup>
import { ref, computed } from 'vue'
import { trustScore } from '../logic/showcase.js'

const reels = ref([
  { id: 'r1', title: 'Lumi Serum — Tokyo Launch', market: 'JP', format: '9:16 · 15s', views: 2840000, cvr: 4.8, roas: 4.2,
    provenance: true, metricsVerified: true, clientAttested: true, complianceGate: true, hue: 262 },
  { id: 'r2', title: 'Northwave — LATAM Signup', market: 'BR', format: '1:1 · 30s', views: 1210000, cvr: 3.1, roas: 3.4,
    provenance: true, metricsVerified: true, clientAttested: false, complianceGate: true, hue: 190 },
  { id: 'r3', title: 'Kaito Beauty — SEA UGC Wave', market: 'SG', format: '9:16 · 12s', views: 5300000, cvr: 5.6, roas: 6.1,
    provenance: true, metricsVerified: true, clientAttested: true, complianceGate: true, hue: 320 },
  { id: 'r4', title: 'Peak Gear — DE Spec Bumper', market: 'EU', format: '16:9 · 6s', views: 640000, cvr: 1.9, roas: 2.2,
    provenance: true, metricsVerified: false, clientAttested: false, complianceGate: true, hue: 152 },
  { id: 'r5', title: 'Solace Home — US Founder POV', market: 'US', format: '9:16 · 22s', views: 980000, cvr: 2.7, roas: 2.9,
    provenance: false, metricsVerified: true, clientAttested: false, complianceGate: true, hue: 28 },
  { id: 'r6', title: 'Aria Audio — KR Before/After', market: 'KR', format: '9:16 · 18s', views: 3100000, cvr: 5.1, roas: 4.7,
    provenance: true, metricsVerified: true, clientAttested: true, complianceGate: false, hue: 210 }
])

const openId = ref(null)
const scored = computed(() => reels.value.map(r => ({ ...r, trust: trustScore(r) })))

const BADGE = {
  verified:      { label: 'Verified',      cls: 'b-verified' },
  substantiated: { label: 'Substantiated', cls: 'b-substant' },
  claimed:       { label: 'Claimed',       cls: 'b-claimed' }
}
const EVIDENCE_LABEL = {
  provenance: 'C2PA content credentials · capture chain intact',
  metricsVerified: 'Metrics pulled from platform APIs, not self-reported',
  clientAttested: 'Client co-signed this case study',
  complianceGate: 'Passed risk & legal gate for its markets'
}

const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(0) + 'K' : String(n)
</script>

<template>
  <div class="gallery">
    <div class="card head">
      <div>
        <div class="kicker">Digital video showcase · proof over promises</div>
        <h3>Verified work, shareable with any prospect</h3>
        <p class="meta">Every reel carries content credentials and an evidence trail — the badge tells a buyer exactly how much of the story is independently verified.</p>
      </div>
    </div>

    <div class="grid">
      <div v-for="r in scored" :key="r.id" class="card reel" @click="openId = openId === r.id ? null : r.id">
        <div class="thumb" :style="{ '--h': r.hue }">
          <div class="bars"><span v-for="i in 5" :key="i" :style="{ animationDelay: (i * .18) + 's' }"></span></div>
          <span class="play">▶</span>
          <span class="fmt">{{ r.format }}</span>
          <span class="badge" :class="BADGE[r.trust.badge].cls">{{ BADGE[r.trust.badge].label }} · {{ r.trust.score }}</span>
        </div>
        <div class="body">
          <div class="title-row">
            <strong>{{ r.title }}</strong>
            <span class="mkt">{{ r.market }}</span>
          </div>
          <div class="stats">
            <span><b>{{ fmt(r.views) }}</b> views</span>
            <span><b>{{ r.cvr.toFixed(1) }}%</b> CVR</span>
            <span><b>{{ r.roas.toFixed(1) }}×</b> ROAS</span>
          </div>
          <transition name="ev">
            <ul v-if="openId === r.id" class="evidence">
              <li v-for="e in r.trust.evidence" :key="e.key" :class="{ ok: e.present }">
                <span class="tick">{{ e.present ? '✓' : '—' }}</span>
                <span>{{ EVIDENCE_LABEL[e.key] }}</span>
                <span class="w">+{{ e.present ? e.weight : 0 }}</span>
              </li>
            </ul>
          </transition>
          <div class="hint">{{ openId === r.id ? 'Click to collapse' : 'Click for evidence trail' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gallery { display: flex; flex-direction: column; gap: 16px; }
.card { padding: 18px; }
.head h3 { margin: 4px 0 6px; }
.meta { color: var(--text-dim); font-size: 13px; margin: 0; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }

.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.reel { padding: 0; overflow: hidden; cursor: pointer; transition: transform .15s, border-color .15s; }
.reel:hover { transform: translateY(-2px); border-color: rgba(124, 92, 255, .4); }

.thumb { position: relative; height: 130px; background:
  linear-gradient(135deg, hsl(var(--h) 70% 22%), hsl(calc(var(--h) + 40) 70% 34%)); display: grid; place-items: center; }
.bars { position: absolute; inset: 0; display: flex; align-items: flex-end; gap: 6%; padding: 0 10%; opacity: .35; }
.bars span { flex: 1; height: 30%; background: #fff; border-radius: 4px 4px 0 0; animation: eq 1.6s ease-in-out infinite alternate; }
@keyframes eq { from { height: 18%; } to { height: 72%; } }
.play { position: relative; width: 40px; height: 40px; border-radius: 50%; background: rgba(255,255,255,.92); color: #111; display: grid; place-items: center; font-size: 13px; padding-left: 3px; }
.fmt { position: absolute; left: 10px; bottom: 8px; font-size: 10px; background: rgba(0,0,0,.45); color: #fff; padding: 2px 8px; border-radius: 999px; }
.badge { position: absolute; right: 10px; top: 8px; font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 999px; }
.b-verified { background: rgba(52, 211, 153, .2); color: #34d399; border: 1px solid rgba(52, 211, 153, .5); }
.b-substant { background: rgba(34, 211, 238, .18); color: #22d3ee; border: 1px solid rgba(34, 211, 238, .45); }
.b-claimed  { background: rgba(255, 255, 255, .12); color: #cbd2e0; border: 1px solid var(--border); }

.body { padding: 12px 14px 14px; }
.title-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 13px; }
.mkt { font-size: 10px; padding: 2px 8px; border-radius: 999px; background: var(--surface-2); color: var(--text-dim); }
.stats { display: flex; gap: 12px; margin-top: 8px; font-size: 11px; color: var(--text-dim); }
.stats b { color: var(--text); font-variant-numeric: tabular-nums; }

.evidence { list-style: none; margin: 10px 0 0; padding: 10px 0 0; border-top: 1px dashed var(--border); display: flex; flex-direction: column; gap: 6px; }
.evidence li { display: grid; grid-template-columns: 18px 1fr auto; gap: 8px; font-size: 11px; color: var(--text-dim); }
.evidence li.ok { color: var(--text); }
.tick { color: #34d399; }
.evidence li:not(.ok) .tick { color: var(--text-dim); }
.w { font-variant-numeric: tabular-nums; color: var(--text-dim); }
.hint { margin-top: 10px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.ev-enter-active { transition: opacity .2s; }
.ev-enter-from { opacity: 0; }

@media (max-width: 1000px) { .grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 640px)  { .grid { grid-template-columns: 1fr; } }
</style>
