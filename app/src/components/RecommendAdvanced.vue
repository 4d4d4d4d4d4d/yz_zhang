<script setup>
import { ref, computed, onMounted } from 'vue'
import WorkerSwarm from './WorkerSwarm.vue'

const fileEl = ref(null)
const imgUrl = ref(null)
const palette = ref(['#7c5cff', '#22d3ee', '#ff7ad9', '#34d399'])
const dragOver = ref(false)

function pickFile() { fileEl.value?.click() }
function onFile(e) {
  const f = e.target.files?.[0] || e.dataTransfer?.files?.[0]
  if (!f) return
  const url = URL.createObjectURL(f)
  imgUrl.value = url
  extractPalette(url)
}
function onDrop(e) {
  e.preventDefault(); dragOver.value = false
  onFile({ dataTransfer: e.dataTransfer })
}

function extractPalette(url) {
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => {
    const c = document.createElement('canvas')
    c.width = 32; c.height = 32
    const ctx = c.getContext('2d')
    ctx.drawImage(img, 0, 0, 32, 32)
    const px = ctx.getImageData(0, 0, 32, 32).data
    const buckets = {}
    for (let i = 0; i < px.length; i += 4) {
      const r = px[i] >> 5, g = px[i + 1] >> 5, b = px[i + 2] >> 5
      const key = `${r}-${g}-${b}`
      buckets[key] = (buckets[key] || { c: 0, r: 0, g: 0, b: 0 })
      buckets[key].c++; buckets[key].r += px[i]; buckets[key].g += px[i + 1]; buckets[key].b += px[i + 2]
    }
    const top = Object.values(buckets).sort((a, b) => b.c - a.c).slice(0, 4)
    palette.value = top.map(b => `rgb(${Math.round(b.r / b.c)},${Math.round(b.g / b.c)},${Math.round(b.b / b.c)})`)
  }
  img.src = url
}

const workers = [
  { name: 'Vision Agent',      lane: 'image+video', color: '#7c5cff' },
  { name: 'Audience Agent',    lane: 'segments',    color: '#22d3ee' },
  { name: 'Brand Voice Agent', lane: 'tonality',    color: '#ff7ad9' },
  { name: 'Market Agent',      lane: 'localization', color: '#34d399' },
  { name: 'Compliance Agent',  lane: 'risk + IP',   color: '#fbbf24' },
  { name: 'Format Agent',      lane: 'platform',    color: '#60a5fa' }
]

const cohorts = [
  { name: 'Gen Z · Urban · JP', size: 1240000, overlap: 18, ctr: 4.8, cvr: 2.6 },
  { name: 'Millennials · US Coastal', size: 980000, overlap: 32, ctr: 3.6, cvr: 3.4 },
  { name: 'K-Beauty enthusiasts', size: 610000, overlap: 41, ctr: 5.4, cvr: 3.1 },
  { name: 'Parents · 28-42 · BR', size: 1450000, overlap: 24, ctr: 3.2, cvr: 4.0 },
  { name: 'Professionals · DE/FR', size: 720000, overlap: 12, ctr: 2.9, cvr: 4.6 }
]

const points = [
  { id: 'A', label: 'UGC Reel', roas: 4.2, cpa: 12, picked: true },
  { id: 'B', label: 'Founder POV', roas: 3.4, cpa: 18 },
  { id: 'C', label: 'Spec Bumper', roas: 2.6, cpa: 22 },
  { id: 'D', label: '7-day Diary', roas: 3.8, cpa: 14 },
  { id: 'E', label: 'Before/After', roas: 4.6, cpa: 16 },
  { id: 'F', label: 'Lookbook', roas: 2.4, cpa: 28 },
  { id: 'G', label: 'ASMR Unbox', roas: 2.0, cpa: 26 }
]

function px(p) {
  return { x: 40 + ((p.cpa - 8) / 24) * 280, y: 180 - ((p.roas - 1.5) / 3.5) * 150 }
}
const pareto = computed(() => {
  const sorted = [...points].sort((a, b) => a.cpa - b.cpa)
  const front = []
  let bestRoas = 0
  for (const p of sorted) {
    if (p.roas > bestRoas) { front.push(p); bestRoas = p.roas }
  }
  return front
})

onMounted(() => {})
</script>

<template>
  <div class="adv">
    <div class="row">
      <div class="card upload"
        :class="{ over: dragOver, has: imgUrl }"
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop="onDrop">
        <input ref="fileEl" type="file" accept="image/*,video/*" hidden @change="onFile" />
        <div v-if="!imgUrl" class="dz" @click="pickFile">
          <div class="dz-icon">⤴</div>
          <div class="dz-title">Drop product image or video</div>
          <div class="dz-sub">PNG, JPG, MP4 · up to 50MB · client-side palette extraction</div>
        </div>
        <div v-else class="preview">
          <img :src="imgUrl" alt="upload" />
          <div class="palette">
            <div v-for="(c, i) in palette" :key="i" class="sw" :style="{ background: c }" :title="c"></div>
          </div>
          <button class="btn btn-ghost sm replace" @click="pickFile" type="button">Replace</button>
        </div>
      </div>

      <WorkerSwarm
        title="Parallel inference pipeline"
        subtitle="6 specialist agents fan out concurrently. Aggregator merges results into ranked concepts."
        :workers="workers"
        :queue-depth="186" />
    </div>

    <div class="row">
      <div class="card">
        <div class="hh">
          <h3>Audience cohorts</h3>
          <span class="meta">{{ cohorts.length }} segments matched</span>
        </div>
        <div class="cohorts">
          <div v-for="c in cohorts" :key="c.name" class="coh">
            <div class="cn">
              <span>{{ c.name }}</span>
              <span class="cs">{{ (c.size / 1000000).toFixed(2) }}M reach</span>
            </div>
            <div class="bars">
              <div class="bar-row">
                <span class="bl">overlap</span>
                <div class="bt"><div class="bf overlap" :style="{ width: c.overlap + '%' }"></div></div>
                <span class="bv">{{ c.overlap }}%</span>
              </div>
              <div class="bar-row">
                <span class="bl">CTR</span>
                <div class="bt"><div class="bf ctr" :style="{ width: (c.ctr * 14) + '%' }"></div></div>
                <span class="bv">{{ c.ctr }}%</span>
              </div>
              <div class="bar-row">
                <span class="bl">CVR</span>
                <div class="bt"><div class="bf cvr" :style="{ width: (c.cvr * 18) + '%' }"></div></div>
                <span class="bv">{{ c.cvr }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="hh">
          <h3>Pareto · ROAS vs CPA</h3>
          <span class="meta">7 candidates · {{ pareto.length }} on frontier</span>
        </div>
        <svg viewBox="0 0 360 220" class="pareto">
          <g stroke="var(--border)" stroke-width="1">
            <line x1="40" y1="180" x2="320" y2="180" />
            <line x1="40" y1="180" x2="40" y2="30" />
          </g>
          <g fill="var(--text-dim)" font-size="9">
            <text x="40" y="200">$8</text>
            <text x="180" y="200" text-anchor="middle">$20</text>
            <text x="320" y="200" text-anchor="end">$32 CPA →</text>
            <text x="34" y="180" text-anchor="end">1.5×</text>
            <text x="34" y="105" text-anchor="end">3.0×</text>
            <text x="34" y="30" text-anchor="end">5.0× ROAS</text>
          </g>
          <polyline
            :points="pareto.map(p => { const { x, y } = px(p); return `${x},${y}` }).join(' ')"
            fill="none" stroke="var(--primary-2)" stroke-width="2" stroke-dasharray="4 4" />
          <g v-for="p in points" :key="p.id">
            <circle :cx="px(p).x" :cy="px(p).y" :r="p.picked ? 7 : 5"
              :fill="p.picked ? 'var(--primary)' : 'var(--surface-2)'"
              :stroke="pareto.includes(p) ? 'var(--primary-2)' : 'var(--border)'" stroke-width="2" />
            <text :x="px(p).x + 10" :y="px(p).y + 3" font-size="10" fill="var(--text)">{{ p.label }}</text>
          </g>
        </svg>
        <div class="legend">
          <span><span class="dot picked"></span>Picked</span>
          <span><span class="dot front"></span>On Pareto frontier</span>
          <span><span class="dot rest"></span>Dominated</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.adv { display: flex; flex-direction: column; gap: 16px; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.upload { padding: 20px; min-height: 280px; display: flex; align-items: stretch; }
.upload.over { border-color: var(--primary); background: rgba(124, 92, 255, .1); }
.dz { width: 100%; border: 2px dashed var(--border); border-radius: 12px; display: grid; place-items: center; cursor: pointer; padding: 32px 20px; text-align: center; gap: 8px; }
.dz:hover { border-color: var(--primary); }
.dz-icon { font-size: 28px; }
.dz-title { font-weight: 600; }
.dz-sub { font-size: 12px; color: var(--text-dim); }

.preview { width: 100%; display: flex; flex-direction: column; gap: 12px; position: relative; }
.preview img { max-height: 200px; border-radius: 10px; object-fit: cover; border: 1px solid var(--border); }
.palette { display: flex; gap: 6px; }
.sw { width: 36px; height: 36px; border-radius: 8px; border: 1px solid var(--border); }
.replace { position: absolute; top: 0; right: 0; padding: 4px 10px; font-size: 11px; }

.hh { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; }
.meta { color: var(--text-dim); font-size: 12px; }

.cohorts { display: flex; flex-direction: column; gap: 12px; }
.coh { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.cn { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 8px; }
.cs { color: var(--text-dim); font-size: 11px; }
.bars { display: flex; flex-direction: column; gap: 4px; }
.bar-row { display: grid; grid-template-columns: 64px 1fr 40px; gap: 8px; align-items: center; font-size: 11px; }
.bl { color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; font-size: 10px; }
.bt { height: 4px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.bf { height: 100%; }
.bf.overlap { background: var(--primary); }
.bf.ctr { background: var(--primary-2); }
.bf.cvr { background: var(--success); }
.bv { color: var(--text); font-variant-numeric: tabular-nums; text-align: right; }

.pareto { width: 100%; height: auto; }
.legend { display: flex; gap: 16px; font-size: 11px; color: var(--text-dim); margin-top: 12px; flex-wrap: wrap; }
.legend .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.legend .dot.picked { background: var(--primary); }
.legend .dot.front { background: transparent; border: 2px solid var(--primary-2); }
.legend .dot.rest { background: var(--surface-2); border: 1px solid var(--border); }

@media (max-width: 1024px) { .row { grid-template-columns: 1fr; } }
</style>
