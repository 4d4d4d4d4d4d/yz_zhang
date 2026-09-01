<script setup>
import { ref, watch, onMounted, onBeforeUnmount, computed } from 'vue'
import { createBandit } from '../logic/bandit.js'

const ARM_META = [
  { id: 'A', name: 'UGC Reel · JP',     truth: 0.052, color: '#7c5cff' },
  { id: 'B', name: 'Founder POV · US',  truth: 0.038, color: '#22d3ee' },
  { id: 'C', name: 'Before/After · KR', truth: 0.061, color: '#ff7ad9' },
  { id: 'D', name: 'Spec Bumper · DE',  truth: 0.028, color: '#34d399' }
]

const bandit = createBandit(ARM_META, { epsilon: 0.15 })

const epsilon = ref(0.15)
const running = ref(true)
const snap = ref(bandit.snapshot())

watch(epsilon, v => bandit.setEpsilon(v))

const arms = computed(() => snap.value.arms.map((a, i) => ({ ...a, ...ARM_META[i] })))
const regret = computed(() => snap.value.regret)
const cumReward = computed(() => snap.value.cumReward)
const cumOptimal = computed(() => snap.value.cumOptimal)
const totalPulls = computed(() => snap.value.totalPulls)

let timer
onMounted(() => {
  timer = setInterval(() => {
    if (!running.value) return
    for (let i = 0; i < 4; i++) bandit.step()
    snap.value = bandit.snapshot()
  }, 150)
})
onBeforeUnmount(() => clearInterval(timer))

function reset() {
  bandit.reset()
  snap.value = bandit.snapshot()
}

const regretPath = computed(() => {
  const w = 360, h = 100
  if (!regret.value.length) return ''
  const max = Math.max(...regret.value, 1)
  const dx = w / (regret.value.length - 1 || 1)
  return regret.value.map((v, i) => {
    const x = i * dx
    const y = h - (v / max) * (h - 6) - 3
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

const best = computed(() => arms.value.slice().sort((a, b) => (b.conv / Math.max(1, b.pulls)) - (a.conv / Math.max(1, a.pulls)))[0])
</script>

<template>
  <div class="bandit">
    <div class="card head">
      <div>
        <div class="kicker">Multi-armed bandit · Thompson + ε-greedy</div>
        <h3>Live creative exploration</h3>
        <p class="meta">Auto-balances traffic toward best-performing arms. Live · {{ totalPulls.toLocaleString() }} impressions decided.</p>
      </div>
      <div class="ctrls">
        <label>ε <input type="range" min="0" max="0.5" step="0.05" v-model.number="epsilon" /> {{ epsilon.toFixed(2) }}</label>
        <button class="btn btn-ghost sm" @click="running = !running" type="button">{{ running ? 'Pause' : 'Resume' }}</button>
        <button class="btn btn-ghost sm" @click="reset" type="button">Reset</button>
      </div>
    </div>

    <div class="grid">
      <div class="card arms">
        <h3>Arms · {{ arms.length }}</h3>
        <div v-for="a in arms" :key="a.id" class="arm" :class="{ best: best && best.id === a.id }">
          <div class="arm-head">
            <span class="arm-name">
              <span class="arm-dot" :style="{ background: a.color }"></span>
              {{ a.id }} · {{ a.name }}
            </span>
            <span class="arm-share">{{ a.share }}% traffic</span>
          </div>
          <div class="arm-track">
            <div class="arm-fill" :style="{ width: a.share + '%', background: a.color }"></div>
          </div>
          <div class="arm-foot">
            <span>{{ a.pulls.toLocaleString() }} pulls</span>
            <span>{{ a.conv.toLocaleString() }} conv</span>
            <span><strong>{{ a.pulls ? (a.conv / a.pulls * 100).toFixed(2) : '0.00' }}%</strong> obs CVR</span>
            <span class="ci">95% CI ±{{ a.pulls ? (1.96 * Math.sqrt((a.conv/a.pulls)*(1 - a.conv/a.pulls) / a.pulls) * 100).toFixed(2) : '—' }}%</span>
          </div>
        </div>
      </div>

      <div class="card regret">
        <h3>Cumulative regret</h3>
        <p class="meta">{{ regret[regret.length - 1] ? regret[regret.length - 1].toFixed(1) : '0.0' }} missed conversions vs optimal arm</p>
        <svg viewBox="0 0 360 100" class="reg-svg" preserveAspectRatio="none">
          <g stroke="var(--border)" stroke-width="1" stroke-dasharray="3 3">
            <line x1="0" y1="50" x2="360" y2="50" />
            <line x1="0" y1="100" x2="360" y2="100" />
          </g>
          <path :d="regretPath" fill="none" stroke="url(#g1)" stroke-width="2.5" stroke-linecap="round" />
          <defs>
            <linearGradient id="g1" x1="0" x2="1">
              <stop offset="0" stop-color="#7c5cff" />
              <stop offset="1" stop-color="#22d3ee" />
            </linearGradient>
          </defs>
        </svg>
        <div class="reg-foot">
          <div><div class="rn">{{ cumReward.toLocaleString() }}</div><div class="rl">Conv</div></div>
          <div><div class="rn">{{ Math.round(cumOptimal).toLocaleString() }}</div><div class="rl">Optimal (oracle)</div></div>
          <div><div class="rn grad-text">{{ cumReward && cumOptimal ? Math.round(cumReward / cumOptimal * 100) : 0 }}%</div><div class="rl">Efficiency</div></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bandit { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; gap: 16px; align-items: center; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.ctrls { display: flex; align-items: center; gap: 14px; }
.ctrls label { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-dim); }
.ctrls input[type="range"] { accent-color: var(--primary); width: 100px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; align-items: flex-start; }

.arms { display: flex; flex-direction: column; gap: 14px; }
.arm { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); transition: border-color .2s; }
.arm.best { border-color: var(--success); background: rgba(52, 211, 153, .06); }
.arm-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.arm-name { font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 8px; }
.arm-dot { width: 10px; height: 10px; border-radius: 50%; }
.arm-share { font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }
.arm-track { height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-bottom: 8px; }
.arm-fill { height: 100%; transition: width .25s ease; }
.arm-foot { display: flex; gap: 18px; font-size: 11px; color: var(--text-dim); flex-wrap: wrap; align-items: center; }
.arm-foot strong { color: var(--text); font-variant-numeric: tabular-nums; }
.ci { margin-left: auto; }

.regret { display: flex; flex-direction: column; }
.reg-svg { width: 100%; height: 120px; margin: 12px 0; }
.reg-foot { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding-top: 12px; border-top: 1px solid var(--border); }
.rn { font-size: 20px; font-weight: 800; font-variant-numeric: tabular-nums; }
.rl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

@media (max-width: 900px) {
  .grid { grid-template-columns: 1fr; }
  .ctrls { width: 100%; }
}
</style>
