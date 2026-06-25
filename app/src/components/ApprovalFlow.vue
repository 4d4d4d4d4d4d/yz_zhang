<script setup>
import { ref } from 'vue'

const deal = ref({ name: 'AdForge × Lumen JP', value: 840000, currency: 'USD' })

const nodes = [
  { id: 'start',    type: 'start', label: 'Deal submitted',    status: 'done',    when: 'Nov 28 09:14', actor: 'AM' },
  { id: 'gate',     type: 'gate',  label: '> $500K?',           status: 'done',    when: 'Nov 28 09:14', actor: 'auto' },
  { id: 'legal',    type: 'task',  label: 'Legal review',       status: 'done',    when: 'Nov 30 16:42', actor: 'Cobalt Legal', sla: '48h', used: '50h · breach 2h' },
  { id: 'finance',  type: 'task',  label: 'Finance review',     status: 'done',    when: 'Nov 29 11:08', actor: 'CFO',           sla: '24h', used: '22h' },
  { id: 'exec',     type: 'task',  label: 'Executive approval', status: 'doing',   when: '—',            actor: 'CEO',           sla: '24h', used: '18h' },
  { id: 'join',     type: 'join',  label: 'All approved',       status: 'pending', when: '—' },
  { id: 'sign',     type: 'task',  label: 'E-sign · all parties', status: 'pending', when: '—', actor: '4 signers', sla: '5d' },
  { id: 'end',      type: 'end',   label: 'Booked',             status: 'pending', when: '—' }
]

const events = [
  { who: 'AM',   what: 'submitted deal for approval', when: 'Nov 28 09:14' },
  { who: 'auto', what: 'routed via > $500K gate to legal + finance + exec', when: 'Nov 28 09:14' },
  { who: 'CFO',  what: 'approved finance review', when: 'Nov 29 11:08', note: 'Margin 43.2% — within target.' },
  { who: 'Cobalt Legal', what: 'redlined exclusivity & data clauses', when: 'Nov 30 16:42', note: 'SLA breach by 2h — flagged to ops.' },
  { who: 'AI · Risk Reviewer', what: 'rescored deal after redline: 92/100 (was 78)', when: 'Nov 30 16:50' },
  { who: 'CEO',  what: 'in review · viewing executive summary', when: '12 min ago' }
]
</script>

<template>
  <div class="flow">
    <div class="card head">
      <div>
        <div class="kicker">Approval workflow</div>
        <h3>{{ deal.name }} · ${{ (deal.value / 1000).toFixed(0) }}k {{ deal.currency }}</h3>
        <p class="meta">Routed via &gt; $500K gate · 3 of 4 approvals collected · 1 SLA breach</p>
      </div>
      <button class="btn btn-ghost sm" type="button">Edit workflow</button>
    </div>

    <div class="card canvas">
      <div class="bpmn">
        <div class="row1">
          <div class="node" :class="['n-' + nodes[0].type, nodes[0].status]">
            <div class="ring"></div>
            <div class="nl">{{ nodes[0].label }}</div>
            <div class="nm">{{ nodes[0].when }} · {{ nodes[0].actor }}</div>
          </div>
          <div class="arrow"></div>
          <div class="node" :class="['n-' + nodes[1].type, nodes[1].status]">
            <div class="diamond"></div>
            <div class="nl">{{ nodes[1].label }}</div>
            <div class="nm">{{ nodes[1].when }} · auto</div>
          </div>
          <div class="arrow"></div>
          <div class="fan">
            <div class="node" :class="['n-' + nodes[2].type, nodes[2].status]">
              <div class="box"></div>
              <div class="nl">{{ nodes[2].label }}</div>
              <div class="nm">{{ nodes[2].actor }} · SLA {{ nodes[2].sla }}</div>
              <div class="sla" :class="nodes[2].status">{{ nodes[2].used }}</div>
            </div>
            <div class="node" :class="['n-' + nodes[3].type, nodes[3].status]">
              <div class="box"></div>
              <div class="nl">{{ nodes[3].label }}</div>
              <div class="nm">{{ nodes[3].actor }} · SLA {{ nodes[3].sla }}</div>
              <div class="sla" :class="nodes[3].status">{{ nodes[3].used }}</div>
            </div>
            <div class="node" :class="['n-' + nodes[4].type, nodes[4].status]">
              <div class="box"></div>
              <div class="nl">{{ nodes[4].label }}</div>
              <div class="nm">{{ nodes[4].actor }} · SLA {{ nodes[4].sla }}</div>
              <div class="sla" :class="nodes[4].status">{{ nodes[4].used }} <span class="pulse">●</span></div>
            </div>
          </div>
        </div>

        <div class="row2">
          <div class="arrow vt"></div>
          <div class="node" :class="['n-' + nodes[5].type, nodes[5].status]">
            <div class="diamond join"></div>
            <div class="nl">{{ nodes[5].label }}</div>
            <div class="nm">{{ nodes[5].when || 'awaiting CEO' }}</div>
          </div>
          <div class="arrow"></div>
          <div class="node" :class="['n-' + nodes[6].type, nodes[6].status]">
            <div class="box"></div>
            <div class="nl">{{ nodes[6].label }}</div>
            <div class="nm">{{ nodes[6].actor }} · SLA {{ nodes[6].sla }}</div>
          </div>
          <div class="arrow"></div>
          <div class="node" :class="['n-' + nodes[7].type, nodes[7].status]">
            <div class="ring end"></div>
            <div class="nl">{{ nodes[7].label }}</div>
          </div>
        </div>
      </div>

      <div class="legend">
        <span><span class="lg done"></span>done</span>
        <span><span class="lg doing"></span>in progress</span>
        <span><span class="lg pending"></span>pending</span>
        <span class="rt">SLA breach flagged on Legal review</span>
      </div>
    </div>

    <div class="card">
      <h3>Activity</h3>
      <ul class="ev">
        <li v-for="(e, i) in events" :key="i">
          <span class="ev-who" :class="{ ai: e.who.startsWith('AI') }">{{ e.who }}</span>
          <span class="ev-what">{{ e.what }}<span v-if="e.note" class="ev-note">— {{ e.note }}</span></span>
          <span class="ev-when">{{ e.when }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.flow { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); margin: 4px 0 0; font-size: 13px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.canvas { padding: 24px; }
.bpmn { display: flex; flex-direction: column; gap: 28px; }
.row1, .row2 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.fan { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; flex: 1; }

.node { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); min-width: 120px; transition: border-color .15s; position: relative; }
.node.done { border-color: rgba(52, 211, 153, .35); background: rgba(52, 211, 153, .04); }
.node.doing { border-color: rgba(251, 191, 36, .45); background: rgba(251, 191, 36, .06); }
.node.pending { opacity: .6; }

.ring { width: 28px; height: 28px; border-radius: 50%; border: 2px solid var(--primary-2); background: var(--bg-2); }
.ring.end { border-width: 4px; border-color: var(--success); }
.box { width: 32px; height: 22px; border-radius: 6px; background: var(--primary); }
.node.done .box { background: var(--success); }
.node.doing .box { background: #fcd34d; animation: blink 1.4s ease-in-out infinite; }
.node.pending .box { background: var(--surface-2); }
.diamond { width: 26px; height: 26px; background: var(--primary); transform: rotate(45deg); }
.diamond.join { background: var(--success); }
.node.pending .diamond { background: var(--surface-2); }

.nl { font-size: 12px; font-weight: 600; text-align: center; }
.nm { font-size: 10px; color: var(--text-dim); text-align: center; }
.sla { margin-top: 4px; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; }
.sla.done { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.sla.doing { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.pulse { color: var(--primary-2); animation: blink 1s ease-in-out infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }

.arrow { width: 28px; height: 2px; background: var(--text-dim); position: relative; flex-shrink: 0; }
.arrow::after { content: ''; position: absolute; right: -1px; top: -3px; border: 4px solid transparent; border-left: 6px solid var(--text-dim); }
.arrow.vt { width: 100%; height: 1px; margin-left: 12px; opacity: .3; }
.arrow.vt::after { display: none; }

.legend { display: flex; gap: 16px; margin-top: 20px; padding-top: 14px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-dim); align-items: center; flex-wrap: wrap; }
.lg { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }
.lg.done { background: var(--success); }
.lg.doing { background: #fcd34d; }
.lg.pending { background: var(--surface-2); }
.rt { margin-left: auto; color: #fcd34d; }

.ev { list-style: none; margin: 14px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.ev li { display: grid; grid-template-columns: 140px 1fr 140px; gap: 12px; padding: 10px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }
.ev li:last-child { border-bottom: 0; }
.ev-who { font-weight: 600; color: var(--text); }
.ev-who.ai { color: var(--primary-2); }
.ev-what { color: var(--text); }
.ev-note { color: var(--text-dim); margin-left: 4px; font-size: 12px; }
.ev-when { color: var(--text-dim); font-size: 12px; text-align: right; }

@media (max-width: 1024px) {
  .fan { grid-template-columns: 1fr; }
  .row1, .row2 { flex-direction: column; align-items: stretch; }
  .arrow { width: 2px; height: 16px; margin: 0 auto; }
  .arrow::after { right: -3px; top: auto; bottom: -1px; border: 4px solid transparent; border-top: 6px solid var(--text-dim); border-left: 4px solid transparent; }
  .ev li { grid-template-columns: 1fr; gap: 2px; }
  .ev-when { text-align: left; }
}
</style>
