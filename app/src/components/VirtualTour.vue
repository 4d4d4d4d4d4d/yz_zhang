<script setup>
import { ref, computed } from 'vue'
import { shortestPath, coverage, pickRendition, validateTour } from '../logic/tour.js'

const TOUR = {
  entrance: 'lobby',
  stations: [
    { id: 'lobby',    name: 'Reception & Lobby',   zone: 'Front of house', hue: 262, captured: '2026-05-18',
      hotspots: [{ to: 'line-a', label: 'Production Line A →' }, { to: 'showroom', label: 'Showroom →' }] },
    { id: 'showroom', name: 'Product Showroom',    zone: 'Front of house', hue: 300, captured: '2026-05-18',
      hotspots: [{ to: 'lobby', label: '← Lobby' }] },
    { id: 'line-a',   name: 'Production Line A',   zone: 'Manufacturing',  hue: 190, captured: '2026-05-19',
      hotspots: [{ to: 'lobby', label: '← Lobby' }, { to: 'line-b', label: 'Line B →' }, { to: 'qa', label: 'QA Lab →' }] },
    { id: 'line-b',   name: 'Production Line B',   zone: 'Manufacturing',  hue: 210, captured: '2026-05-19',
      hotspots: [{ to: 'line-a', label: '← Line A' }, { to: 'warehouse', label: 'Warehouse →' }] },
    { id: 'qa',       name: 'QA & Testing Lab',    zone: 'Quality',        hue: 152, captured: '2026-05-19',
      hotspots: [{ to: 'line-a', label: '← Line A' }, { to: 'cleanroom', label: 'Clean Room →' }] },
    { id: 'cleanroom',name: 'Clean Room',          zone: 'Quality',        hue: 140, captured: '2026-05-20',
      hotspots: [{ to: 'qa', label: '← QA Lab' }] },
    { id: 'warehouse',name: 'Warehouse & Logistics', zone: 'Logistics',    hue: 28,  captured: '2026-05-20',
      hotspots: [{ to: 'line-b', label: '← Line B' }] }
  ]
}

const RENDITIONS = [
  { id: '8k-vr', label: '8K VR', minMbps: 50 },
  { id: '4k',    label: '4K',    minMbps: 25 },
  { id: '1080p', label: '1080p', minMbps: 8 },
  { id: '720p',  label: '720p',  minMbps: 3 }
]

const current = ref('lobby')
const visited = ref(['lobby'])
const bandwidth = ref(30)
const guideTarget = ref('cleanroom')

const station = computed(() => TOUR.stations.find(s => s.id === current.value))
const cov = computed(() => coverage(visited.value, TOUR))
const rendition = computed(() => pickRendition(bandwidth.value, RENDITIONS))
const health = computed(() => validateTour(TOUR))
const guidePath = computed(() => shortestPath(TOUR, current.value, guideTarget.value))

function go(id) {
  current.value = id
  if (!visited.value.includes(id)) visited.value.push(id)
}
</script>

<template>
  <div class="vt">
    <div class="card head">
      <div>
        <div class="kicker">Virtual factory tour · captured on site, walked online</div>
        <h3>Bring the buyer to the plant — without the flight</h3>
        <p class="meta">3D capture from {{ station.captured }} · graph {{ health.ok ? 'validated ✓' : 'has issues' }} · navigation follows real walkways, so the visit feels like a visit.</p>
      </div>
      <label class="bw">Link speed
        <input type="range" min="1" max="60" v-model.number="bandwidth" /> {{ bandwidth }} Mbps → <b>{{ rendition.label }}</b>
      </label>
    </div>

    <div class="grid">
      <div class="card pano" :style="{ '--h': station.hue }">
        <div class="pano-bg">
          <div class="grid-floor"></div>
          <div class="glow"></div>
        </div>
        <div class="pano-head">
          <span class="zone">{{ station.zone }}</span>
          <h3>{{ station.name }}</h3>
          <span class="cap">📷 captured {{ station.captured }} · {{ rendition.label }} stream</span>
        </div>
        <div class="hotspots">
          <button v-for="h in station.hotspots" :key="h.to" type="button" class="hs" @click="go(h.to)">
            {{ h.label }}
          </button>
        </div>
      </div>

      <div class="side">
        <div class="card mini">
          <div class="kicker">Coverage · {{ cov.percent }}%</div>
          <div class="bar"><div class="fill" :style="{ width: cov.percent + '%' }"></div></div>
          <div v-for="(z, name) in cov.zones" :key="name" class="zrow">
            <span>{{ name }}</span><b>{{ z.visited }}/{{ z.total }}</b>
          </div>
          <p v-if="cov.missed.length" class="missed">Not yet shown: {{ cov.missed.map(m => m.name).join(', ') }}</p>
          <p v-else class="done">Full plant covered ✓</p>
        </div>

        <div class="card mini">
          <div class="kicker">Guide me to…</div>
          <select v-model="guideTarget">
            <option v-for="s in TOUR.stations" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
          <div v-if="guidePath" class="path">
            <span v-for="(p, i) in guidePath" :key="p" class="step" :class="{ here: i === 0 }">
              {{ TOUR.stations.find(s => s.id === p).name }}<span v-if="i < guidePath.length - 1"> →</span>
            </span>
          </div>
        </div>

        <div class="card mini map">
          <div class="kicker">Stations</div>
          <button v-for="s in TOUR.stations" :key="s.id" type="button"
            class="node" :class="{ on: s.id === current, seen: visited.includes(s.id) }" @click="go(s.id)">
            {{ s.name }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vt { display: flex; flex-direction: column; gap: 16px; }
.card { padding: 18px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; flex-wrap: wrap; }
.head h3 { margin: 4px 0 6px; }
.meta { color: var(--text-dim); font-size: 13px; margin: 0; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 8px; }
.bw { font-size: 11px; color: var(--text-dim); display: flex; align-items: center; gap: 8px; }
.bw b { color: var(--text); }

.grid { display: grid; grid-template-columns: 7fr 5fr; gap: 14px; align-items: start; }

.pano { position: relative; min-height: 380px; overflow: hidden; display: flex; flex-direction: column; justify-content: space-between; }
.pano-bg { position: absolute; inset: 0; background: linear-gradient(180deg, hsl(var(--h) 55% 12%), hsl(var(--h) 45% 7%)); }
.grid-floor { position: absolute; left: -20%; right: -20%; bottom: -10%; height: 60%;
  background-image: linear-gradient(hsl(var(--h) 70% 40% / .35) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--h) 70% 40% / .35) 1px, transparent 1px);
  background-size: 44px 44px; transform: perspective(420px) rotateX(58deg); animation: drift 14s linear infinite; }
@keyframes drift { from { background-position: 0 0, 0 0; } to { background-position: 0 88px, 88px 0; } }
.glow { position: absolute; top: 12%; left: 50%; width: 55%; height: 40%; transform: translateX(-50%);
  background: radial-gradient(ellipse, hsl(var(--h) 80% 55% / .28), transparent 70%); }
.pano-head { position: relative; }
.zone { font-size: 10px; text-transform: uppercase; letter-spacing: .1em; color: hsl(var(--h) 80% 70%); }
.pano-head h3 { margin: 6px 0 4px; font-size: 24px; }
.cap { font-size: 11px; color: var(--text-dim); }
.hotspots { position: relative; display: flex; flex-wrap: wrap; gap: 10px; }
.hs { padding: 10px 16px; border-radius: 999px; border: 1px solid hsl(var(--h) 70% 55% / .5); background: hsl(var(--h) 60% 30% / .35); color: #fff; font-size: 13px; cursor: pointer; backdrop-filter: blur(4px); }
.hs:hover { background: hsl(var(--h) 60% 40% / .5); }

.side { display: flex; flex-direction: column; gap: 12px; }
.mini { padding: 14px; }
.bar { height: 8px; border-radius: 999px; background: var(--surface-2); overflow: hidden; margin-bottom: 10px; }
.fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); transition: width .3s; }
.zrow { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-dim); padding: 3px 0; }
.zrow b { color: var(--text); }
.missed { font-size: 11px; color: #fbbf24; margin: 8px 0 0; }
.done { font-size: 11px; color: #34d399; margin: 8px 0 0; }

select { width: 100%; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 12px; }
.path { margin-top: 10px; font-size: 11px; color: var(--text-dim); line-height: 1.8; }
.step.here { color: #22d3ee; }

.map { display: flex; flex-direction: column; }
.node { text-align: left; padding: 8px 10px; margin-top: 4px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text-dim); font-size: 12px; cursor: pointer; }
.node.seen { border-color: rgba(52, 211, 153, .35); }
.node.on { border-color: rgba(124, 92, 255, .55); background: rgba(124, 92, 255, .14); color: #fff; }

@media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } }
</style>
