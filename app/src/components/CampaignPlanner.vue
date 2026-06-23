<script setup>
import { ref } from 'vue'

const phases = [
  { name: 'Week 1 · Seed', items: ['10 hero variants', 'Top 3 markets', 'Soft launch — JP, US, KR'], pct: 18 },
  { name: 'Week 2 · Optimize', items: ['Auto A/B winners', 'Add subtitles · 12 languages', 'Voiceover localization'], pct: 36 },
  { name: 'Week 3 · Scale', items: ['Expand to LATAM + SEA', '40 variants live', 'Pipe winners to ad accounts'], pct: 64 },
  { name: 'Week 4 · Review', items: ['Performance report', 'Creative refresh', 'Next-quarter plan'], pct: 100 }
]
const active = ref(0)
</script>

<template>
  <div class="planner card">
    <div class="left">
      <div class="kicker">Auto-generated plan</div>
      <h3>Q4 launch · global</h3>
      <p class="meta">$240,000 budget · 8 markets · 60 variants</p>
      <div class="track">
        <div class="bar" :style="{ width: phases[active].pct + '%' }"></div>
      </div>
      <div class="phases">
        <button v-for="(p, i) in phases" :key="i"
          class="phase" :class="{ on: active === i }"
          @click="active = i" type="button">
          <div class="phase-name">{{ p.name }}</div>
          <div class="phase-pct">{{ p.pct }}%</div>
        </button>
      </div>
    </div>
    <div class="right">
      <div class="kicker">Phase tasks</div>
      <h3>{{ phases[active].name }}</h3>
      <ul>
        <li v-for="(it, i) in phases[active].items" :key="i">
          <span class="check">✓</span>{{ it }}
        </li>
      </ul>
      <div class="footer">
        <span class="dot"></span> AI is monitoring 4 ad accounts in real time.
      </div>
    </div>
  </div>
</template>

<style scoped>
.planner { display: grid; grid-template-columns: 1.2fr 1fr; gap: 32px; padding: 32px; }
.kicker { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 8px; }
.meta { color: var(--text-dim); margin: 8px 0 20px; }
.track { height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-bottom: 16px; }
.bar { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); border-radius: 999px; transition: width .4s ease; }

.phases { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.phase {
  text-align: left; padding: 14px 16px; border-radius: 12px;
  background: var(--surface); border: 1px solid var(--border); color: var(--text); cursor: pointer;
}
.phase.on { border-color: var(--primary); background: rgba(124, 92, 255, .12); }
.phase-name { font-weight: 600; font-size: 14px; }
.phase-pct { font-size: 12px; color: var(--text-dim); margin-top: 4px; }

.right ul { list-style: none; margin: 0; padding: 0; }
.right li { padding: 10px 0; border-bottom: 1px dashed var(--border); color: var(--text); font-size: 15px; display: flex; gap: 10px; }
.right li:last-child { border-bottom: 0; }
.check { color: var(--success); font-weight: 700; }
.footer { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border); color: var(--text-dim); font-size: 13px; display: inline-flex; gap: 8px; align-items: center; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 12px var(--success); animation: p 1.5s ease-in-out infinite; }
@keyframes p { 0%,100% { opacity: 1; } 50% { opacity: .4; } }

@media (max-width: 900px) { .planner { grid-template-columns: 1fr; } }
</style>
