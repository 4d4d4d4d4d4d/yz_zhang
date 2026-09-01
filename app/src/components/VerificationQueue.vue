<script setup>
import { ref, computed } from 'vue'
import { createQueue } from '../logic/showcase.js'

const limit = ref(3)
const tasks = ref([])
const stats = ref({ inFlight: 0, queued: 0, done: 0, failed: 0 })
let queue = createQueue(limit.value)
let idSeq = 0
let busy = false

const STEPS = ['Provenance hash check', 'Platform metrics pull', 'Compliance gate']
const PRIORITY_LABEL = { 3: 'deal-blocking', 2: 'client-facing', 1: 'routine' }

const delay = ms => new Promise(r => setTimeout(r, ms))

function rebuildQueue() {
  // New limit applies to the next batch; in-flight work drains on the old queue.
  queue = createQueue(limit.value)
}

async function runBatch(n = 8) {
  if (busy) return
  busy = true
  const batch = []
  for (let i = 0; i < n; i++) {
    const priority = 1 + Math.floor(Math.random() * 3)
    const entry = ref({
      id: ++idSeq,
      name: `Reel #${idSeq} · ${STEPS[idSeq % STEPS.length]}`,
      priority,
      status: 'queued',
      ms: 0
    })
    tasks.value.unshift(entry.value)
    if (tasks.value.length > 24) tasks.value.pop()

    const p = queue.enqueue(async () => {
      entry.value.status = 'running'
      const started = performance.now()
      await delay(400 + Math.random() * 900)
      entry.value.ms = Math.round(performance.now() - started)
      if (Math.random() < 0.12) throw new Error('verification mismatch')
    }, { priority })
      .then(() => { entry.value.status = 'done' })
      .catch(() => { entry.value.status = 'failed' })
      .finally(() => { stats.value = queue.stats() })
    stats.value = queue.stats()
    batch.push(p)
  }
  await Promise.allSettled(batch)
  stats.value = queue.stats()
  busy = false
}

const saturation = computed(() => Math.round((stats.value.inFlight / limit.value) * 100))
</script>

<template>
  <div class="vq">
    <div class="card head">
      <div>
        <div class="kicker">Verification pipeline · bounded concurrency</div>
        <h3>Worker pool with priority & back-pressure</h3>
        <p class="meta">At most <b>{{ limit }}</b> verifications in flight — deal-blocking work jumps the line, arrivals stay FIFO within a class, and a failed check never leaks its slot.</p>
      </div>
      <div class="ctrls">
        <label>Workers
          <input type="range" min="1" max="6" step="1" v-model.number="limit" @change="rebuildQueue" />
          {{ limit }}
        </label>
        <button class="btn btn-primary sm" type="button" @click="runBatch(8)">Run batch · 8</button>
      </div>
    </div>

    <div class="stats">
      <div class="card stat"><span class="n">{{ stats.inFlight }}</span><span class="l">in flight</span>
        <div class="track"><div class="fill" :style="{ width: saturation + '%' }"></div></div>
      </div>
      <div class="card stat"><span class="n">{{ stats.queued }}</span><span class="l">queued (back-pressure)</span></div>
      <div class="card stat"><span class="n ok">{{ stats.done }}</span><span class="l">verified</span></div>
      <div class="card stat"><span class="n bad">{{ stats.failed }}</span><span class="l">failed · slot released</span></div>
    </div>

    <div class="card list">
      <h3>Recent checks</h3>
      <p v-if="!tasks.length" class="meta">Run a batch to watch the scheduler work.</p>
      <div v-for="t in tasks" :key="t.id" class="task" :class="t.status">
        <span class="dot"></span>
        <span class="name">{{ t.name }}</span>
        <span class="pri" :class="'p' + t.priority">{{ PRIORITY_LABEL[t.priority] }}</span>
        <span class="ms">{{ t.status === 'done' || t.status === 'failed' ? t.ms + 'ms' : t.status }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vq { display: flex; flex-direction: column; gap: 16px; }
.card { padding: 18px; }
.head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; flex-wrap: wrap; }
.head h3 { margin: 4px 0 6px; }
.meta { color: var(--text-dim); font-size: 13px; margin: 0; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.ctrls { display: flex; align-items: center; gap: 12px; }
.ctrls label { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-dim); }
.btn.sm { padding: 7px 14px; font-size: 12px; }

.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat { display: flex; flex-direction: column; gap: 4px; }
.n { font-size: 26px; font-weight: 800; font-variant-numeric: tabular-nums; }
.n.ok { color: #34d399; } .n.bad { color: #f87171; }
.l { font-size: 11px; color: var(--text-dim); }
.track { height: 6px; border-radius: 999px; background: var(--surface-2); overflow: hidden; margin-top: 6px; }
.fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); transition: width .25s; }

.list h3 { margin: 0 0 10px; }
.task { display: grid; grid-template-columns: 10px 1fr auto auto; gap: 10px; align-items: center; padding: 8px 4px; border-bottom: 1px dashed var(--border); font-size: 12px; }
.task:last-child { border-bottom: 0; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-dim); }
.task.running .dot { background: #22d3ee; animation: pulse 1s infinite alternate; }
.task.done .dot { background: #34d399; }
.task.failed .dot { background: #f87171; }
@keyframes pulse { from { opacity: .4; } to { opacity: 1; } }
.name { color: var(--text); }
.pri { font-size: 10px; padding: 2px 8px; border-radius: 999px; background: var(--surface-2); color: var(--text-dim); }
.ms { font-variant-numeric: tabular-nums; color: var(--text-dim); font-size: 11px; }
.task.failed .ms { color: #f87171; }

@media (max-width: 800px) { .stats { grid-template-columns: repeat(2, 1fr); } }
</style>
