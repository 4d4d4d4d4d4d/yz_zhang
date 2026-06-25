<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  title: { type: String, default: 'Worker swarm' },
  subtitle: { type: String, default: '' },
  workers: {
    type: Array,
    required: true
    /* each: { name, lane, color } */
  },
  queueDepth: { type: Number, default: 142 }
})

const ticks = ref(props.workers.map(w => ({
  name: w.name, lane: w.lane, color: w.color,
  state: 'idle', progress: 0, jobs: Math.floor(Math.random() * 240 + 80),
  success: 95 + Math.random() * 4, latencyMs: 0
})))

const totalJobs = ref(ticks.value.reduce((s, t) => s + t.jobs, 0))
const queue = ref(props.queueDepth)

let timer
onMounted(() => {
  timer = setInterval(() => {
    for (const t of ticks.value) {
      if (t.state === 'idle') {
        if (Math.random() < 0.6) {
          t.state = 'running'; t.progress = 0
          t.latencyMs = Math.round(120 + Math.random() * 800)
        }
      } else {
        t.progress = Math.min(100, t.progress + 8 + Math.random() * 14)
        if (t.progress >= 100) {
          t.state = 'idle'; t.jobs += 1
          totalJobs.value += 1
          queue.value = Math.max(0, queue.value - 1)
          if (queue.value < 60) queue.value += Math.floor(Math.random() * 6)
        }
      }
    }
  }, 220)
})
onBeforeUnmount(() => clearInterval(timer))

const concurrent = () => ticks.value.filter(t => t.state === 'running').length
</script>

<template>
  <div class="swarm card">
    <div class="sh">
      <div>
        <div class="kicker">Concurrency</div>
        <h3>{{ title }}</h3>
        <p v-if="subtitle" class="sub">{{ subtitle }}</p>
      </div>
      <div class="metrics">
        <div><div class="mn grad-text">{{ concurrent() }}<span class="of">/{{ workers.length }}</span></div><div class="ml">Workers active</div></div>
        <div><div class="mn">{{ totalJobs.toLocaleString() }}</div><div class="ml">Jobs / hr</div></div>
        <div><div class="mn">{{ queue }}</div><div class="ml">Queue depth</div></div>
      </div>
    </div>

    <div class="lanes">
      <div v-for="t in ticks" :key="t.name" class="lane">
        <div class="ln-head">
          <span class="ln-name"><span class="ln-dot" :style="{ background: t.color }"></span>{{ t.name }}</span>
          <span class="ln-meta">{{ t.lane }} · {{ Math.round(t.success * 10) / 10 }}% ok</span>
        </div>
        <div class="track">
          <div class="fill" :style="{ width: t.progress + '%', background: t.color }"></div>
        </div>
        <div class="ln-foot">
          <span class="ln-state" :class="t.state">{{ t.state === 'running' ? '● running' : '○ idle' }}</span>
          <span class="ln-jobs">{{ t.jobs }} jobs · {{ t.latencyMs }}ms p95</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.swarm { padding: 20px; }
.sh { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.sub { color: var(--text-dim); margin: 4px 0 0; font-size: 13px; }
.metrics { display: flex; gap: 18px; }
.mn { font-size: 22px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.of { font-size: 13px; color: var(--text-dim); }
.ml { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.lanes { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.lane { padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.ln-head { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px; }
.ln-name { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; }
.ln-dot { width: 8px; height: 8px; border-radius: 50%; }
.ln-meta { color: var(--text-dim); font-size: 11px; }
.track { height: 4px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.fill { height: 100%; transition: width .1s linear; }
.ln-foot { display: flex; justify-content: space-between; font-size: 11px; margin-top: 6px; color: var(--text-dim); }
.ln-state.running { color: var(--success); }

@media (max-width: 720px) { .lanes { grid-template-columns: 1fr; } }
</style>
