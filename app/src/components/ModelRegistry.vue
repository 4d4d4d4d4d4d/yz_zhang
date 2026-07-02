<script setup>
import { ref, computed } from 'vue'

const models = ref([
  { id: 'rec-v17', created: 'Dec 02', algo: 'two-tower + reranker', params: '124M', ndcg: 0.482, drift: 0.06, status: 'canary', traffic: 10, ctr: [3.2, 3.4, 3.6, 3.8, 4.0, 4.2, 4.5], note: 'New JP audience tower' },
  { id: 'rec-v16', created: 'Nov 18', algo: 'two-tower + reranker', params: '118M', ndcg: 0.461, drift: 0.04, status: 'prod',   traffic: 90, ctr: [3.4, 3.5, 3.6, 3.6, 3.5, 3.7, 3.8], note: 'Stable baseline' },
  { id: 'rec-v15', created: 'Oct 30', algo: 'two-tower',            params: '102M', ndcg: 0.438, drift: 0.11, status: 'shadow', traffic: 0,  ctr: [3.1, 3.2, 3.2, 3.0, 2.9, 2.8, 2.8], note: 'Drift on US cohort' },
  { id: 'rec-v14', created: 'Oct 12', algo: 'gbdt + content',       params: '38M',  ndcg: 0.402, drift: 0.18, status: 'archived', traffic: 0, ctr: [3.0, 2.9, 2.8, 2.6, 2.5, 2.4, 2.3], note: 'Deprecated' }
])

const selected = ref('rec-v17')
const cur = computed(() => models.value.find(m => m.id === selected.value))

function promote() {
  const c = cur.value
  if (c.status !== 'canary') return
  const prod = models.value.find(m => m.status === 'prod')
  if (prod) { prod.status = 'shadow'; prod.traffic = 0 }
  c.status = 'prod'; c.traffic = 100
}
function rollback() {
  const c = cur.value
  if (c.status !== 'canary') return
  c.status = 'shadow'; c.traffic = 0
}
function setTraffic(v) {
  if (cur.value.status !== 'canary') return
  cur.value.traffic = v
  const prod = models.value.find(m => m.status === 'prod')
  if (prod) prod.traffic = 100 - v
}

function spark(arr, w = 80, h = 24) {
  const max = Math.max(...arr), min = Math.min(...arr)
  const dx = w / (arr.length - 1)
  return arr.map((v, i) => {
    const x = i * dx
    const y = h - ((v - min) / (max - min || 1)) * (h - 4) - 2
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}
</script>

<template>
  <div class="reg">
    <div class="card head">
      <div>
        <div class="kicker">Model registry</div>
        <h3>Recommendation models · 4 versions</h3>
        <p class="meta">{{ cur.id }} · {{ cur.algo }} · {{ cur.params }} params · NDCG@10 = {{ cur.ndcg.toFixed(3) }}</p>
      </div>
      <div class="actions">
        <button class="btn btn-ghost sm" :disabled="cur.status !== 'canary'" @click="rollback" type="button">Rollback</button>
        <button class="btn btn-primary sm" :disabled="cur.status !== 'canary'" @click="promote" type="button">Promote → prod</button>
      </div>
    </div>

    <div class="card">
      <table class="t">
        <thead>
          <tr>
            <th>Model</th>
            <th>Created</th>
            <th class="num">NDCG@10</th>
            <th class="num">Drift</th>
            <th>Online CTR (7d)</th>
            <th>Traffic</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in models" :key="m.id"
            :class="{ on: selected === m.id }"
            @click="selected = m.id">
            <td>
              <div class="m-id">{{ m.id }}</div>
              <div class="m-note">{{ m.note }}</div>
            </td>
            <td class="dimc">{{ m.created }}</td>
            <td class="num"><strong>{{ m.ndcg.toFixed(3) }}</strong></td>
            <td class="num"><span class="drift" :class="m.drift < 0.08 ? 'ok' : m.drift < 0.15 ? 'warn' : 'risk'">{{ (m.drift * 100).toFixed(1) }}%</span></td>
            <td>
              <svg viewBox="0 0 80 24" class="sp" preserveAspectRatio="none">
                <path :d="spark(m.ctr)" fill="none" stroke="var(--primary-2)" stroke-width="2" stroke-linecap="round" />
              </svg>
            </td>
            <td><span class="tr-bar"><span class="tr-fill" :style="{ width: m.traffic + '%' }"></span></span><span class="tr-num">{{ m.traffic }}%</span></td>
            <td><span class="st" :class="m.status">{{ m.status }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card canary" v-if="cur.status === 'canary'">
      <div class="ch-row">
        <h3>Canary · {{ cur.id }}</h3>
        <span class="meta">Adjust live traffic split. Prod model receives the remainder.</span>
      </div>
      <div class="split">
        <div class="split-track">
          <div class="split-canary" :style="{ width: cur.traffic + '%' }"><span>{{ cur.id }} · {{ cur.traffic }}%</span></div>
          <div class="split-prod"><span>prod · {{ 100 - cur.traffic }}%</span></div>
        </div>
        <input type="range" min="0" max="100" :value="cur.traffic" @input="setTraffic(+$event.target.value)" />
      </div>
      <div class="canary-foot">
        <div><div class="cn">+{{ ((cur.ndcg - 0.461) / 0.461 * 100).toFixed(1) }}%</div><div class="cl">NDCG lift vs prod</div></div>
        <div><div class="cn">{{ (cur.drift * 100).toFixed(1) }}%</div><div class="cl">Feature drift</div></div>
        <div><div class="cn">{{ (cur.traffic * 124).toLocaleString() }}</div><div class="cl">Req / s</div></div>
        <div><div class="cn ok-color">98.4%</div><div class="cl">Guardrail pass</div></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reg { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); margin: 4px 0 0; font-size: 13px; }
.actions { display: flex; gap: 8px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }
.btn.sm:disabled { opacity: .4; cursor: not-allowed; }

.t { width: 100%; border-collapse: collapse; font-size: 13px; }
.t th { text-align: left; padding: 10px 12px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.t th.num { text-align: right; }
.t td { padding: 12px; border-bottom: 1px dashed var(--border); cursor: pointer; }
.t td.num { text-align: right; font-variant-numeric: tabular-nums; }
.t td.dimc { color: var(--text-dim); font-size: 12px; }
.t tr:hover td { background: rgba(124, 92, 255, .04); }
.t tr.on td { background: rgba(124, 92, 255, .12); }
.m-id { font-family: ui-monospace, monospace; font-weight: 700; color: var(--primary-2); }
.m-note { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
.drift { padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; }
.drift.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.drift.warn { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.drift.risk { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.sp { width: 80px; height: 24px; }
.tr-bar { display: inline-block; vertical-align: middle; width: 70px; height: 5px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-right: 8px; }
.tr-fill { display: block; height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.tr-num { font-variant-numeric: tabular-nums; font-size: 12px; }
.st { font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.st.prod { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.st.canary { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.st.shadow { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.st.archived { background: var(--surface-2); color: var(--text-dim); }

.canary { padding: 20px; }
.ch-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; gap: 16px; flex-wrap: wrap; }
.split { margin-bottom: 16px; }
.split-track { display: flex; height: 36px; border-radius: 10px; overflow: hidden; border: 1px solid var(--border); }
.split-canary { background: linear-gradient(135deg, rgba(251, 191, 36, .35), rgba(255, 122, 217, .35)); display: grid; place-items: center; color: #fff; font-size: 12px; font-weight: 700; min-width: 80px; transition: width .2s ease; }
.split-prod { flex: 1; background: linear-gradient(135deg, rgba(124, 92, 255, .25), rgba(34, 211, 238, .25)); display: grid; place-items: center; color: #fff; font-size: 12px; font-weight: 700; }
.split input { width: 100%; accent-color: var(--primary); margin-top: 12px; }

.canary-foot { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding-top: 16px; border-top: 1px solid var(--border); }
.cn { font-size: 20px; font-weight: 800; font-variant-numeric: tabular-nums; }
.ok-color { color: var(--success); }
.cl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

@media (max-width: 900px) {
  .t th:nth-child(2), .t td:nth-child(2),
  .t th:nth-child(5), .t td:nth-child(5) { display: none; }
  .canary-foot { grid-template-columns: 1fr 1fr; }
}
</style>
