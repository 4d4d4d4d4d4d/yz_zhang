<script setup>
import { ref, computed } from 'vue'
import WorkerSwarm from './WorkerSwarm.vue'
import { discountZopa, surplusSplit, discountAnchor } from '../logic/negotiation.js'

// Spec 49 — the zone is defined by the two RESERVATIONS (walk-away points);
// targets are aspirations and sit outside it. Computed by the logic layer:
// the previous inline formula mixed targets with reservations and multiplied
// by 1.1, so the band's v-if was always false and it never rendered.
const zopa = {
  yourTarget: 38,        // seller aspiration — smallest discount you'd love
  yourReservation: 52,   // seller walk-away — most discount you'll concede
  theirReservation: 44,  // buyer walk-away — least discount they'll accept
  theirTarget: 58,       // buyer aspiration
  scale: { min: 30, max: 65, unit: '% off MSRP', label: 'Wholesale discount' }
}
function pct(v) { return ((v - zopa.scale.min) / (zopa.scale.max - zopa.scale.min)) * 100 }

const zone = computed(() => discountZopa(zopa.theirReservation, zopa.yourReservation))
const settlement = ref(zone.value.midpoint ?? 48)
const split = computed(() => surplusSplit(zone.value, settlement.value))
const anchors = computed(() => ({
  seller: discountAnchor(zone.value, 'seller'),
  buyer: discountAnchor(zone.value, 'buyer')
}))

const presence = [
  { initials: 'AM', name: 'Akiko Mori',     role: 'AdForge — COO',  status: 'editing',  color: '#7c5cff' },
  { initials: 'KT', name: 'Kenji Tanaka',   role: 'AdForge — CEO',  status: 'viewing',  color: '#22d3ee' },
  { initials: 'HY', name: 'Hiro Yamazaki',  role: 'Lumen Studios',  status: 'viewing',  color: '#ff7ad9' },
  { initials: 'CL', name: 'Cobalt Legal',   role: 'External counsel', status: 'idle',  color: '#34d399' }
]

const workers = [
  { name: 'Clause Analyst',  lane: 'parse + compare', color: '#7c5cff' },
  { name: 'Localization',    lane: 'JP / EN parity',  color: '#22d3ee' },
  { name: 'Risk Reviewer',   lane: 'IP · liability',  color: '#ff7ad9' },
  { name: 'Margin Modeler',  lane: 'P&L sim',         color: '#34d399' },
  { name: 'Precedent Search', lane: 'cross-deal',     color: '#fbbf24' }
]

const clauseTitle = '§ 4.2 — Wholesale pricing & rebate structure'
const diff = [
  { t: 'eq',  s: 'Distributor shall purchase the Products from Supplier at the wholesale price equal to MSRP less ' },
  { t: 'del', s: 'fifty-five percent (55%)' },
  { t: 'ins', s: 'forty-eight percent (48%)' },
  { t: 'eq',  s: ', payable net thirty (30) days from invoice. ' },
  { t: 'del', s: 'A volume rebate of five percent (5%) shall apply on quarterly purchases above 3,000 units.' },
  { t: 'ins', s: 'A volume rebate of four percent (4%) shall apply on quarterly purchases above 5,000 units, calculated and paid quarterly in arrears.' },
  { t: 'eq',  s: ' ' },
  { t: 'ins', s: 'Either party may review pricing if MSRP changes by more than ten percent (10%).' }
]

const comments = [
  { who: 'Akiko Mori', when: '14m ago', text: 'Holding the 48% — anything lower breaks margin floor.', kind: 'comment' },
  { who: 'AI · Margin Modeler', when: '13m ago', text: 'At 48% gross margin holds at 43.2%. At 50% margin drops to 41.1% (yellow zone).', kind: 'ai' },
  { who: 'Hiro Yamazaki', when: '8m ago', text: '48% works if rebate threshold drops to 4,000 units.', kind: 'comment' },
  { who: 'AI · Precedent Search', when: '7m ago', text: 'Comparable JP DTC deals: 47–50% discount with 4–6% rebate (n=12).', kind: 'ai' }
]

const draft = ref('')
function postComment() {
  if (!draft.value.trim()) return
  comments.push({ who: 'You', when: 'just now', text: draft.value, kind: 'comment' })
  draft.value = ''
}
</script>

<template>
  <div class="play">
    <div class="card">
      <div class="h-row">
        <div>
          <div class="kicker">Active clause</div>
          <h3>{{ clauseTitle }}</h3>
        </div>
        <div class="presence">
          <span v-for="p in presence" :key="p.initials" class="av"
            :style="{ background: p.color }" :class="p.status"
            :title="`${p.name} · ${p.role} · ${p.status}`">{{ p.initials }}</span>
        </div>
      </div>

      <div class="zopa">
        <div class="kicker">BATNA · ZOPA · Target / Reservation</div>
        <div class="z-scale">
          <div class="z-track">
            <div class="z-zopa" v-if="zone.exists && zone.width > 0"
              :style="{ left: pct(zone.low) + '%', width: (pct(zone.high) - pct(zone.low)) + '%' }">
              <span>ZOPA</span>
            </div>
            <div class="z-settle" :style="{ left: pct(split ? split.settlement : zone.midpoint) + '%' }"
              :title="`Settlement ${settlement}%`"></div>
            <div class="z-mk you-res" :style="{ left: pct(zopa.yourReservation) + '%' }"><span>Your reservation</span></div>
            <div class="z-mk you-tar" :style="{ left: pct(zopa.yourTarget) + '%' }"><span>Your target</span></div>
            <div class="z-mk them-tar" :style="{ left: pct(zopa.theirTarget) + '%' }"><span>Their target</span></div>
            <div class="z-mk them-res" :style="{ left: pct(zopa.theirReservation) + '%' }"><span>Their reservation</span></div>
          </div>
          <div class="z-axis">
            <span>{{ zopa.scale.min }}%</span>
            <span>{{ Math.round((zopa.scale.min + zopa.scale.max) / 2) }}%</span>
            <span>{{ zopa.scale.max }}%</span>
          </div>
        </div>

        <div class="surplus" v-if="split">
          <label class="s-slider">
            Settlement
            <input type="range" :min="zone.low" :max="zone.high" step="0.5" v-model.number="settlement" />
            <strong>{{ settlement }}%</strong>
          </label>
          <div class="s-bar" :title="`You ${(split.sellerShare*100).toFixed(0)}% · Partner ${(split.buyerShare*100).toFixed(0)}%`">
            <div class="s-you" :style="{ width: (split.sellerShare * 100) + '%' }"></div>
            <div class="s-them" :style="{ width: (split.buyerShare * 100) + '%' }"></div>
          </div>
          <div class="s-legend">
            <span>You capture <strong>{{ (split.sellerShare * 100).toFixed(0) }}%</strong> of the zone</span>
            <span class="dimc">Zone {{ zone.low }}–{{ zone.high }}% · width {{ zone.width }}pt</span>
            <span>Partner <strong>{{ (split.buyerShare * 100).toFixed(0) }}%</strong></span>
          </div>
          <p class="s-anchor">Suggested opening anchors — you {{ anchors.seller.toFixed(1) }}% · partner {{ anchors.buyer.toFixed(1) }}%</p>
        </div>
        <div class="z-legend">
          <span><span class="dot you"></span>You</span>
          <span><span class="dot them"></span>Partner</span>
          <span><span class="dot zopa"></span>Overlap (ZOPA)</span>
          <span class="zhint">Aim for {{ zone.exists ? zone.midpoint : '—' }}% — mid of overlap zone.</span>
        </div>
      </div>
    </div>

    <div class="row">
      <div class="card diff">
        <div class="h-row">
          <h3>Redline · v2 → v3</h3>
          <div class="actions">
            <button class="mini" type="button">← prev</button>
            <button class="mini" type="button">next →</button>
            <button class="btn btn-primary sm" type="button">Accept all AI</button>
          </div>
        </div>
        <div class="doc">
          <template v-for="(d, i) in diff" :key="i">
            <span v-if="d.t === 'eq'">{{ d.s }}</span>
            <del v-else-if="d.t === 'del'">{{ d.s }}</del>
            <ins v-else>{{ d.s }}</ins>
          </template>
        </div>
        <div class="diff-stats">
          <span>{{ diff.filter(d => d.t === 'ins').length }} insertions</span>
          <span>{{ diff.filter(d => d.t === 'del').length }} deletions</span>
          <span class="ok">Margin sim: <strong>43.2%</strong></span>
          <span class="ok">Risk: <strong>OK</strong></span>
        </div>
      </div>

      <WorkerSwarm
        title="AI sub-agents"
        subtitle="Five specialists watch every clause edit; results stream into the comment thread."
        :workers="workers"
        :queue-depth="62" />
    </div>

    <div class="card comments">
      <h3>Discussion · {{ clauseTitle }}</h3>
      <div class="cthread">
        <div v-for="(c, i) in comments" :key="i" class="cm" :class="c.kind">
          <div class="cm-head">
            <span class="cm-who">{{ c.who }}</span>
            <span class="cm-when">{{ c.when }}</span>
          </div>
          <div class="cm-text">{{ c.text }}</div>
        </div>
      </div>
      <form class="cin" @submit.prevent="postComment">
        <input v-model="draft" placeholder="Reply… (Ctrl+Enter to send)" aria-label="Reply to the deal thread" />
        <button class="btn btn-primary sm" type="submit">Post</button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.play { display: flex; flex-direction: column; gap: 16px; }
.h-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 12px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; font-weight: 700; }

.presence { display: flex; gap: -8px; }
.av { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; color: #fff; font-weight: 700; font-size: 11px; border: 2px solid var(--bg); margin-left: -8px; cursor: help; position: relative; }
.av:first-child { margin-left: 0; }
.av.editing::after { content: ''; position: absolute; right: -2px; bottom: -2px; width: 10px; height: 10px; border-radius: 50%; background: var(--success); border: 2px solid var(--bg); }
.av.viewing { opacity: .9; }
.av.idle { opacity: .4; }

.zopa { padding-top: 14px; border-top: 1px solid var(--border); margin-top: 4px; }
.z-settle { position: absolute; top: -4px; bottom: -4px; width: 2px; background: var(--text); z-index: 3; }
.surplus { margin-top: 22px; padding-top: 14px; border-top: 1px dashed var(--border); }
.s-slider { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-dim); }
.s-slider input { flex: 1; accent-color: var(--primary); }
.s-slider strong { color: var(--text); font-variant-numeric: tabular-nums; min-width: 48px; text-align: right; }
.s-bar { display: flex; height: 10px; border-radius: 999px; overflow: hidden; margin-top: 10px; background: var(--surface-2); }
.s-you { background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.s-them { background: rgba(255, 122, 217, .6); }
.s-legend { display: flex; justify-content: space-between; gap: 12px; font-size: 11px; margin-top: 6px; flex-wrap: wrap; }
.s-legend .dimc { color: var(--text-dim); }
.s-anchor { font-size: 11px; color: var(--text-dim); margin: 8px 0 0; }
.z-scale { padding: 60px 0 8px; position: relative; }
.z-track { position: relative; height: 6px; background: var(--surface-2); border-radius: 999px; }
.z-zopa { position: absolute; top: -10px; bottom: -10px; background: linear-gradient(135deg, rgba(124,92,255,.3), rgba(34,211,238,.3)); border: 1px solid rgba(124,92,255,.5); border-radius: 8px; display: grid; place-items: center; font-size: 11px; color: #fff; font-weight: 700; letter-spacing: .08em; }
.z-mk { position: absolute; top: -50px; bottom: -10px; width: 2px; background: var(--text-dim); }
.z-mk::before { content: ''; position: absolute; left: -5px; top: -1px; width: 12px; height: 12px; border-radius: 50%; }
.z-mk.you-res::before, .z-mk.you-tar::before { background: var(--primary); }
.z-mk.them-tar::before, .z-mk.them-res::before { background: var(--accent); }
.z-mk span { position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%); font-size: 10px; color: var(--text); white-space: nowrap; padding: 3px 8px; border-radius: 4px; background: var(--surface); border: 1px solid var(--border); }
.z-axis { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-dim); margin-top: 8px; }
.z-legend { display: flex; gap: 16px; font-size: 11px; color: var(--text-dim); margin-top: 12px; align-items: center; flex-wrap: wrap; }
.z-legend .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.z-legend .dot.you { background: var(--primary); }
.z-legend .dot.them { background: var(--accent); }
.z-legend .dot.zopa { background: linear-gradient(135deg, rgba(124,92,255,.6), rgba(34,211,238,.6)); }
.zhint { margin-left: auto; color: var(--primary-2); font-weight: 600; }

.row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; align-items: flex-start; }
.diff .actions { display: flex; gap: 6px; }
.mini { padding: 4px 10px; border-radius: 6px; background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 11px; cursor: pointer; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.doc { padding: 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; font-family: ui-serif, Georgia, 'Noto Serif', serif; font-size: 14px; line-height: 1.7; color: var(--text); }
.doc del { background: rgba(248, 113, 113, .15); color: #fca5a5; text-decoration: line-through; padding: 0 3px; border-radius: 3px; }
.doc ins { background: rgba(52, 211, 153, .15); color: #6ee7b7; text-decoration: none; padding: 0 3px; border-radius: 3px; }
.diff-stats { display: flex; gap: 16px; padding-top: 12px; margin-top: 12px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-dim); flex-wrap: wrap; }
.diff-stats .ok { color: var(--success); }
.diff-stats strong { color: var(--text); }

.cthread { display: flex; flex-direction: column; gap: 12px; margin: 14px 0 16px; }
.cm { padding: 12px 14px; border-radius: 10px; background: var(--surface); border: 1px solid var(--border); }
.cm.ai { background: linear-gradient(180deg, rgba(124,92,255,.08), rgba(34,211,238,.04)); border-color: rgba(124,92,255,.3); }
.cm-head { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; }
.cm-who { font-weight: 600; }
.cm.ai .cm-who { color: var(--primary-2); }
.cm-when { color: var(--text-dim); }
.cm-text { font-size: 13px; color: var(--text); line-height: 1.55; }

.cin { display: flex; gap: 8px; }
.cin input { flex: 1; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; color: var(--text); font-size: 13px; outline: none; }
.cin input:focus { border-color: var(--primary); }

@media (max-width: 1024px) { .row { grid-template-columns: 1fr; } }
</style>
