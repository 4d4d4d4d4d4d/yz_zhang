<script setup>
import { ref, computed } from 'vue'

const deal = {
  name: 'AdForge × Lumen Studios — JP Distribution',
  parties: ['AdForge K.K.', 'Lumen Studios Tokyo'],
  value: '$840,000 / yr',
  closeBy: 'Dec 15',
  stage: 'Redline'
}

const stages = ['Discovery', 'Proposal', 'Redline', 'Sign', 'Closed']
const stageIdx = stages.indexOf(deal.stage)

const clauses = ref([
  {
    id: 'exclusivity', title: 'Exclusivity',
    you: 'Non-exclusive distribution in JP retail.',
    them: 'Exclusive in JP across all channels for 36 months.',
    ai: 'Exclusive in JP brick-and-mortar only, 24 months, with renewal review.',
    risk: 'warn', accepted: null
  },
  {
    id: 'pricing', title: 'Pricing / Discount',
    you: 'Wholesale at MSRP −42%.',
    them: 'MSRP −55% with 5% quarterly rebate.',
    ai: 'MSRP −48% with 4% rebate above 5,000 units/quarter. Margin floor protected.',
    risk: 'ok', accepted: null
  },
  {
    id: 'ip', title: 'IP indemnity',
    you: 'Mutual indemnity, capped at fees paid.',
    them: 'One-sided indemnity, uncapped.',
    ai: 'Mutual indemnity, capped at 12 months fees. Add IP escrow clause.',
    risk: 'risk', accepted: null
  },
  {
    id: 'data', title: 'Data / Privacy',
    you: 'DPA per APPI, data hosted in JP.',
    them: 'No DPA; partner CRM in US.',
    ai: 'Sign APPI-compliant DPA. SCCs for any cross-border flow. Data minimization clause.',
    risk: 'risk', accepted: null
  },
  {
    id: 'term', title: 'Term & Termination',
    you: '12 months, 60-day notice.',
    them: '36 months, 12-month notice.',
    ai: '24 months, 90-day termination for cause, 180-day for convenience.',
    risk: 'warn', accepted: null
  }
])

function accept(c, who) { c.accepted = who }

const acceptedCount = computed(() => clauses.value.filter(c => c.accepted).length)
const progress = computed(() => Math.round((acceptedCount.value / clauses.value.length) * 100))

const activity = [
  { who: 'AdForge', what: 'sent proposal v2 with redlines on Exclusivity, IP and Data', when: 'Today 09:14', kind: 'proposal' },
  { who: 'Deal Copilot', what: 'flagged 2 risk-level clauses (IP, Data) and drafted 5 suggested rewrites', when: 'Today 09:15', kind: 'ai' },
  { who: 'Lumen Studios', what: 'opened the room and reviewed Exclusivity (12 min)', when: 'Today 10:32', kind: 'partner' },
  { who: 'AdForge Legal', what: 'left a comment on Term clause: "tie to launch milestones"', when: 'Today 11:08', kind: 'comment' },
  { who: 'Deal Copilot', what: 'translated the latest redline to 日本語 for partner review', when: 'Today 11:22', kind: 'ai' }
]

const signers = [
  { name: 'Kenji Tanaka', role: 'CEO, AdForge K.K.', status: 'signed', when: 'Dec 02' },
  { name: 'Akiko Mori',   role: 'COO, AdForge K.K.', status: 'signed', when: 'Dec 02' },
  { name: 'Hiro Yamazaki', role: 'Founder, Lumen Studios', status: 'pending', when: '—' },
  { name: 'Cobalt Legal', role: 'External counsel', status: 'pending', when: '—' }
]

const lang = ref('en')
const langs = [{ v: 'en', l: 'English' }, { v: 'ja', l: '日本語' }, { v: 'zh', l: '中文' }]
</script>

<template>
  <div class="room">
    <div class="card head">
      <div class="top">
        <div>
          <div class="kicker">Deal room</div>
          <h3>{{ deal.name }}</h3>
          <div class="parties">
            <span v-for="p in deal.parties" :key="p" class="party">{{ p }}</span>
          </div>
        </div>
        <div class="meta">
          <div><div class="mn">{{ deal.value }}</div><div class="ml">Annual value</div></div>
          <div><div class="mn">{{ deal.closeBy }}</div><div class="ml">Target close</div></div>
          <div><div class="mn grad-text">{{ progress }}%</div><div class="ml">Terms aligned</div></div>
        </div>
      </div>
      <div class="stages">
        <div v-for="(s, i) in stages" :key="s" class="stage" :class="{ done: i < stageIdx, on: i === stageIdx }">
          <span class="sd">{{ i + 1 }}</span><span>{{ s }}</span>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card terms">
        <div class="th">
          <h3>Term comparison</h3>
          <div class="lang">
            <button v-for="l in langs" :key="l.v" :class="{ on: lang === l.v }" @click="lang = l.v" type="button">{{ l.l }}</button>
          </div>
        </div>
        <div class="trow head-row">
          <div class="tcol">Clause</div>
          <div class="tcol">Your position</div>
          <div class="tcol">Partner position</div>
          <div class="tcol ai-col">AI suggestion</div>
        </div>
        <div v-for="c in clauses" :key="c.id" class="trow">
          <div class="tcol">
            <div class="ttitle">{{ c.title }}</div>
            <span class="risk" :class="c.risk">{{ c.risk === 'ok' ? 'OK' : c.risk === 'warn' ? 'Caution' : 'Risk' }}</span>
          </div>
          <div class="tcol pos" :class="{ chosen: c.accepted === 'you' }">
            <p>{{ c.you }}</p>
            <button class="mini" @click="accept(c, 'you')" type="button">{{ c.accepted === 'you' ? '✓ kept' : 'Keep' }}</button>
          </div>
          <div class="tcol pos" :class="{ chosen: c.accepted === 'them' }">
            <p>{{ c.them }}</p>
            <button class="mini" @click="accept(c, 'them')" type="button">{{ c.accepted === 'them' ? '✓ accepted' : 'Accept' }}</button>
          </div>
          <div class="tcol pos ai-col" :class="{ chosen: c.accepted === 'ai' }">
            <p>{{ c.ai }}</p>
            <button class="mini primary" @click="accept(c, 'ai')" type="button">{{ c.accepted === 'ai' ? '✓ applied' : 'Apply AI' }}</button>
          </div>
        </div>
      </div>

      <div class="side">
        <div class="card">
          <h3>Activity</h3>
          <div class="timeline">
            <div v-for="(a, i) in activity" :key="i" class="event" :class="a.kind">
              <span class="dot"></span>
              <div>
                <div class="ev-top"><strong>{{ a.who }}</strong> {{ a.what }}</div>
                <div class="ev-when">{{ a.when }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <h3>E-signatures</h3>
          <div v-for="s in signers" :key="s.name" class="signer">
            <div>
              <div class="sname">{{ s.name }}</div>
              <div class="srole">{{ s.role }}</div>
            </div>
            <div class="ssig">
              <span class="sstatus" :class="s.status">{{ s.status === 'signed' ? '✓ signed' : '○ pending' }}</span>
              <div class="swhen">{{ s.when }}</div>
            </div>
          </div>
          <div class="sign-actions">
            <button class="btn btn-primary" type="button">Send for signature</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.room { display: flex; flex-direction: column; gap: 20px; }
.head { padding: 24px; }
.top { display: grid; grid-template-columns: 1fr auto; gap: 24px; align-items: flex-start; margin-bottom: 20px; }
.kicker { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 4px; }
.parties { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.party { padding: 4px 10px; border-radius: 6px; background: var(--surface-2); font-size: 12px; border: 1px solid var(--border); }
.meta { display: flex; gap: 20px; }
.mn { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
.ml { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 2px; }

.stages { display: flex; gap: 8px; padding-top: 16px; border-top: 1px solid var(--border); flex-wrap: wrap; }
.stage { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px 6px 6px; border-radius: 999px; border: 1px solid var(--border); font-size: 13px; color: var(--text-dim); }
.sd { width: 22px; height: 22px; border-radius: 50%; background: var(--surface-2); color: var(--text-dim); display: grid; place-items: center; font-size: 11px; font-weight: 700; }
.stage.done { background: rgba(52, 211, 153, .1); border-color: rgba(52, 211, 153, .3); color: #6ee7b7; }
.stage.done .sd { background: var(--success); color: #0a0a0f; }
.stage.on { background: rgba(124, 92, 255, .15); border-color: rgba(124, 92, 255, .4); color: #fff; }
.stage.on .sd { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; align-items: flex-start; }
.terms { padding: 0; }
.th { padding: 20px 24px; display: flex; justify-content: space-between; align-items: center; }
.lang { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; }
.lang button { padding: 5px 10px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 12px; }
.lang button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.trow { display: grid; grid-template-columns: 1.2fr 2fr 2fr 2.4fr; gap: 12px; padding: 16px 24px; border-top: 1px solid var(--border); align-items: flex-start; }
.head-row { padding: 12px 24px; background: rgba(0,0,0,.2); font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.head-row .tcol { padding: 0; }
.tcol p { margin: 0 0 8px; font-size: 13px; line-height: 1.5; }
.ttitle { font-weight: 600; font-size: 14px; margin-bottom: 6px; }
.risk { font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.risk.ok { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.risk.warn { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.risk.risk { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.pos { padding: 12px; border-radius: 10px; background: var(--surface); border: 1px solid var(--border); }
.pos.chosen { border-color: var(--primary); background: rgba(124, 92, 255, .12); }
.ai-col.pos { background: linear-gradient(180deg, rgba(124,92,255,.08), rgba(34,211,238,.04)); border-color: rgba(124,92,255,.3); }
.mini { padding: 5px 10px; border-radius: 6px; background: var(--surface-2); border: 1px solid var(--border); color: var(--text); font-size: 11px; cursor: pointer; }
.mini.primary { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; border: 0; }
.mini:hover { filter: brightness(1.1); }

.side { display: flex; flex-direction: column; gap: 16px; position: sticky; top: 90px; }
.timeline { display: flex; flex-direction: column; gap: 14px; margin-top: 12px; position: relative; }
.timeline::before { content: ''; position: absolute; left: 4px; top: 4px; bottom: 4px; width: 1px; background: var(--border); }
.event { display: flex; gap: 14px; position: relative; }
.event .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--text-dim); margin-top: 4px; flex-shrink: 0; position: relative; z-index: 1; }
.event.ai .dot { background: var(--primary-2); box-shadow: 0 0 8px var(--primary-2); }
.event.proposal .dot { background: var(--primary); }
.event.partner .dot { background: var(--success); }
.event.comment .dot { background: var(--accent); }
.ev-top { font-size: 13px; line-height: 1.5; color: var(--text); }
.ev-top strong { color: #fff; }
.ev-when { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

.signer { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px dashed var(--border); }
.signer:last-of-type { border-bottom: 0; }
.sname { font-weight: 600; font-size: 14px; }
.srole { font-size: 12px; color: var(--text-dim); }
.ssig { text-align: right; }
.sstatus { font-size: 12px; font-weight: 700; }
.sstatus.signed { color: var(--success); }
.sstatus.pending { color: var(--text-dim); }
.swhen { font-size: 11px; color: var(--text-dim); }
.sign-actions { margin-top: 16px; }
.sign-actions :deep(.btn) { width: 100%; justify-content: center; }

@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; }
  .side { position: static; }
  .trow { grid-template-columns: 1fr; }
  .head-row { display: none; }
}
</style>
