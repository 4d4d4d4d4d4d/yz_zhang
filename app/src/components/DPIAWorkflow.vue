<script setup>
import { ref, computed } from 'vue'

const dpia = ref({
  id: 'DPIA-2025-014',
  title: 'AI-generated localized ads · JP / KR / SEA',
  scope: 'Processing of customer-uploaded photos and engagement signals to generate localized ad creatives via AI.',
  lawful_basis: 'Legitimate interest · contractual necessity for ad delivery',
  created: 'Nov 12 2025',
  controller: 'AdForge K.K.',
  dpo: 'Akiko Mori'
})

const steps = ref([
  {
    n: 1, key: 'scope', title: 'Scope & data flows',
    status: 'done', when: 'Nov 12',
    items: [
      { t: 'Inventory of personal data categories', done: true },
      { t: 'Data flow diagram across processors',    done: true },
      { t: 'Retention schedule defined',             done: true }
    ],
    evidence: ['scope-doc-v3.pdf', 'flow-diagram.svg']
  },
  {
    n: 2, key: 'necessity', title: 'Necessity & proportionality',
    status: 'done', when: 'Nov 15',
    items: [
      { t: 'Lawful basis documented',                done: true },
      { t: 'Data minimization assessed',             done: true },
      { t: 'Less-intrusive alternatives reviewed',   done: true }
    ],
    evidence: ['necessity-memo.pdf']
  },
  {
    n: 3, key: 'risks', title: 'Risk identification',
    status: 'done', when: 'Nov 18',
    items: [
      { t: '7 risks identified (3 high · 2 med · 2 low)', done: true },
      { t: 'Likelihood / impact scored',                  done: true },
      { t: 'Affected data subjects mapped',               done: true }
    ],
    evidence: ['risk-register-v2.xlsx']
  },
  {
    n: 4, key: 'mitigations', title: 'Mitigations & residual risk',
    status: 'doing', when: '—',
    items: [
      { t: 'Mitigation owners assigned',           done: true },
      { t: 'Residual risk re-scored',              done: true },
      { t: 'Engineering sign-off on SCC + encryption', done: false },
      { t: 'AI Safety sign-off on PII filter',     done: false }
    ],
    evidence: []
  },
  {
    n: 5, key: 'dpo', title: 'DPO consultation',
    status: 'pending', when: '—',
    items: [
      { t: 'DPO review meeting scheduled', done: false },
      { t: 'DPO opinion documented',        done: false }
    ],
    evidence: []
  },
  {
    n: 6, key: 'publish', title: 'Sign-off & publication',
    status: 'pending', when: '—',
    items: [
      { t: 'Approval by Controller',                 done: false },
      { t: 'Filed in Trust Center · public excerpt', done: false }
    ],
    evidence: []
  }
])

const progress = computed(() => {
  const all = steps.value.reduce((s, st) => s + st.items.length, 0)
  const done = steps.value.reduce((s, st) => s + st.items.filter(i => i.done).length, 0)
  return Math.round((done / all) * 100)
})

const active = ref(4)
</script>

<template>
  <div class="dp">
    <div class="card head">
      <div>
        <div class="kicker">DPIA · {{ dpia.id }}</div>
        <h3>{{ dpia.title }}</h3>
        <p class="meta">Controller {{ dpia.controller }} · DPO {{ dpia.dpo }} · created {{ dpia.created }}</p>
      </div>
      <div class="prog">
        <div class="prog-num grad-text">{{ progress }}%</div>
        <div class="prog-lbl">complete</div>
        <div class="prog-bar"><div class="prog-fill" :style="{ width: progress + '%' }"></div></div>
      </div>
    </div>

    <div class="grid">
      <div class="card stepper">
        <h3>Workflow</h3>
        <div class="track">
          <div v-for="(s, i) in steps" :key="s.key"
            class="st" :class="[s.status, { on: active === i + 1 }]"
            @click="active = s.n">
            <div class="st-num">
              <span v-if="s.status === 'done'">✓</span>
              <span v-else>{{ s.n }}</span>
            </div>
            <div class="st-body">
              <div class="st-head">
                <span class="st-title">{{ s.title }}</span>
                <span class="st-when">{{ s.when }}</span>
              </div>
              <div class="st-meta">{{ s.items.filter(i => i.done).length }} / {{ s.items.length }} tasks done · {{ s.evidence.length }} evidence</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card detail">
        <div class="d-head">
          <div>
            <div class="kicker">Step {{ active }} · {{ steps[active-1].status }}</div>
            <h3>{{ steps[active-1].title }}</h3>
          </div>
          <div class="badges">
            <span class="bd" :class="steps[active-1].status">{{ steps[active-1].status }}</span>
          </div>
        </div>

        <div class="kicker">Tasks</div>
        <ul class="tasks">
          <li v-for="(it, i) in steps[active-1].items" :key="i" :class="{ done: it.done }">
            <span class="cb">{{ it.done ? '✓' : '○' }}</span>
            <span>{{ it.t }}</span>
          </li>
        </ul>

        <div class="kicker">Evidence</div>
        <div class="evi" v-if="steps[active-1].evidence.length">
          <span v-for="f in steps[active-1].evidence" :key="f" class="file">📄 {{ f }}</span>
        </div>
        <div v-else class="empty">No evidence attached yet</div>

        <div class="kicker">Sign-offs required</div>
        <div class="signoffs" v-if="active === 4">
          <div class="so done"><span>✓</span>Eng · SRE</div>
          <div class="so"><span>○</span>Eng · Crypto lead</div>
          <div class="so"><span>○</span>AI Safety</div>
        </div>
        <div v-else-if="active === 5" class="signoffs">
          <div class="so"><span>○</span>DPO · Akiko Mori</div>
        </div>
        <div v-else-if="active === 6" class="signoffs">
          <div class="so"><span>○</span>Controller · CEO</div>
          <div class="so"><span>○</span>Trust Center publish bot</div>
        </div>
        <div v-else class="empty">All sign-offs collected</div>

        <div class="d-actions">
          <button class="btn btn-primary sm" :disabled="steps[active-1].status === 'pending'" type="button">Advance step</button>
          <button class="btn btn-ghost sm" type="button">Add evidence</button>
          <button class="btn btn-ghost sm" type="button">Request review</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dp { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 24px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); margin: 4px 0 0; font-size: 13px; }
.prog { text-align: right; min-width: 200px; }
.prog-num { font-size: 32px; font-weight: 800; line-height: 1; }
.prog-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }
.prog-bar { width: 200px; height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-top: 10px; margin-left: auto; }
.prog-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }

.grid { display: grid; grid-template-columns: 1fr 1.4fr; gap: 16px; align-items: flex-start; }

.stepper { padding: 18px; }
.track { display: flex; flex-direction: column; gap: 4px; margin-top: 12px; position: relative; }
.track::before { content: ''; position: absolute; left: 17px; top: 16px; bottom: 16px; width: 1px; background: var(--border); }
.st { display: grid; grid-template-columns: 36px 1fr; gap: 12px; align-items: center; padding: 10px; border-radius: 10px; cursor: pointer; transition: background .15s; position: relative; }
.st:hover { background: var(--surface); }
.st.on { background: rgba(124, 92, 255, .1); }
.st-num { width: 32px; height: 32px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; font-weight: 700; font-size: 13px; color: var(--text-dim); position: relative; z-index: 1; }
.st.done .st-num { background: var(--success); color: #0a0a0f; }
.st.doing .st-num { background: #fcd34d; color: #0a0a0f; }
.st-head { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }
.st-title { font-weight: 600; font-size: 13px; }
.st-when { font-size: 11px; color: var(--text-dim); }
.st-meta { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

.detail { padding: 20px; }
.d-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 8px; }
.badges { display: flex; gap: 6px; }
.bd { font-size: 11px; padding: 3px 10px; border-radius: 6px; text-transform: uppercase; letter-spacing: .06em; font-weight: 700; }
.bd.done { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.bd.doing { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.bd.pending { background: var(--surface-2); color: var(--text-dim); }

.tasks { list-style: none; padding: 0; margin: 8px 0 18px; display: flex; flex-direction: column; gap: 6px; }
.tasks li { display: flex; gap: 10px; align-items: center; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); font-size: 13px; }
.cb { width: 18px; height: 18px; border-radius: 4px; background: var(--surface-2); display: grid; place-items: center; font-size: 11px; font-weight: 800; color: var(--text-dim); }
.tasks li.done .cb { background: var(--success); color: #0a0a0f; }

.evi { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 18px; }
.file { padding: 5px 12px; border-radius: 6px; background: var(--surface-2); border: 1px solid var(--border); font-size: 12px; }
.empty { padding: 12px; border: 1px dashed var(--border); border-radius: 8px; color: var(--text-dim); font-size: 12px; text-align: center; margin: 8px 0 18px; }

.signoffs { display: flex; flex-direction: column; gap: 6px; margin: 8px 0 18px; }
.so { display: flex; gap: 10px; align-items: center; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); font-size: 13px; color: var(--text-dim); }
.so.done { color: var(--success); border-color: rgba(52, 211, 153, .35); background: rgba(52, 211, 153, .06); }
.so span { font-weight: 800; }

.d-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn.sm { padding: 6px 12px; font-size: 12px; }
.btn.sm:disabled { opacity: .4; cursor: not-allowed; }

@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; }
}
</style>
