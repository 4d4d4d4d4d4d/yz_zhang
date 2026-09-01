<script setup>
import { ref, computed } from 'vue'
import { matchSpecialists, createCase, advanceCase, addEvidence, verifyChain, CASE_STATES } from '../logic/fieldVerify.js'

const SPECIALISTS = [
  { id: 'sp1', name: 'Tanaka Riku',  country: 'JP', crossBorder: ['KR'], languages: ['ja', 'en'],       expertise: ['manufacturing', 'quality'], availableInDays: 3,  rating: 4.9, cases: 61 },
  { id: 'sp2', name: 'Kim Haeun',    country: 'KR', crossBorder: [],     languages: ['ko', 'en', 'ja'], expertise: ['licensing', 'finance'],     availableInDays: 5,  rating: 4.8, cases: 44 },
  { id: 'sp3', name: 'Nguyen Thao',  country: 'VN', crossBorder: ['TH'], languages: ['vi', 'en', 'zh'], expertise: ['manufacturing', 'labor'],   availableInDays: 2,  rating: 4.7, cases: 52 },
  { id: 'sp4', name: 'Ana Souza',    country: 'BR', crossBorder: [],     languages: ['pt', 'es', 'en'], expertise: ['licensing', 'quality'],     availableInDays: 9,  rating: 4.9, cases: 38 },
  { id: 'sp5', name: 'Ito Sakura',   country: 'JP', crossBorder: [],     languages: ['ja', 'zh', 'en'], expertise: ['finance', 'quality'],       availableInDays: 12, rating: 4.6, cases: 29 }
]

const country = ref('JP')
const urgency = ref(7)
const wantLangs = ref(['en', 'ja'])
const wantExp = ref(['manufacturing', 'quality'])

const request = computed(() => ({
  country: country.value, languages: wantLangs.value, expertise: wantExp.value, urgencyDays: urgency.value
}))
const matches = computed(() => matchSpecialists(request.value, SPECIALISTS))

// live case demo
const kase = ref(createCase({ id: 'FV-2087', country: 'JP', subject: 'Kaito Beauty — supplier audit (Osaka plant)' }))
const log = ref([])

const nextState = computed(() => CASE_STATES[CASE_STATES.indexOf(kase.value.state) + 1] || null)
const chain = computed(() => verifyChain(kase.value))

function advance() {
  if (!nextState.value) return
  const r = advanceCase(kase.value, nextState.value)
  log.value.unshift(r.ok
    ? { ok: true, msg: `→ ${kase.value.state}` }
    : { ok: false, msg: r.reason })
}
function tryskip() {
  const target = CASE_STATES[CASE_STATES.indexOf(kase.value.state) + 2]
  if (!target) return
  const r = advanceCase(kase.value, target)
  log.value.unshift({ ok: r.ok, msg: r.ok ? `→ ${target}` : `blocked: ${r.reason}` })
}
const EVIDENCE_TYPES = ['site-photo', 'license-scan', 'interview-note', 'production-video']
function collect() {
  const type = EVIDENCE_TYPES[kase.value.evidence.length % EVIDENCE_TYPES.length]
  const item = addEvidence(kase.value, { type, ref: `${type}-${kase.value.evidence.length + 1}.bin` })
  log.value.unshift({ ok: true, msg: `evidence #${item.seq} sealed · ${item.hash}` })
}
function tamper() {
  if (!kase.value.evidence.length) return
  kase.value.evidence[0].ref = 'edited-after-the-fact.bin'
  log.value.unshift({ ok: false, msg: 'evidence #0 was mutated — watch the chain' })
}

const toggle = (list, v) => { const i = list.indexOf(v); i >= 0 ? list.splice(i, 1) : list.push(v) }
</script>

<template>
  <div class="fv">
    <div class="card head">
      <div>
        <div class="kicker">Field verification · 线下专员跨国调查</div>
        <h3>When the deal needs boots on the ground</h3>
        <p class="meta">Vetted local specialists walk the site, sight the licenses and seal every piece of evidence into a tamper-evident chain. Country coverage is a hard filter — on-site work is never assigned remotely.</p>
      </div>
    </div>

    <div class="grid">
      <div class="card req">
        <div class="kicker">Investigation request</div>
        <div class="f-row">
          <label>Country
            <select v-model="country"><option>JP</option><option>KR</option><option>VN</option><option>BR</option><option>TH</option></select>
          </label>
          <label>Needed within
            <select v-model.number="urgency"><option :value="3">3 days</option><option :value="7">7 days</option><option :value="14">14 days</option></select>
          </label>
        </div>
        <div class="kicker">Languages</div>
        <button v-for="l in ['en','ja','ko','zh','vi','pt','es']" :key="l" type="button" class="chip" :class="{ on: wantLangs.includes(l) }" @click="toggle(wantLangs, l)">{{ l }}</button>
        <div class="kicker" style="margin-top:12px">Expertise</div>
        <button v-for="e in ['manufacturing','quality','licensing','finance','labor']" :key="e" type="button" class="chip" :class="{ on: wantExp.includes(e) }" @click="toggle(wantExp, e)">{{ e }}</button>

        <div class="kicker" style="margin-top:16px">Matched specialists · {{ matches.length }}</div>
        <p v-if="!matches.length" class="none">No specialist covers {{ country }} — we escalate to the partner network instead of assigning remote.</p>
        <div v-for="m in matches" :key="m.specialist.id" class="spec">
          <div class="s-top">
            <b>{{ m.specialist.name }}</b>
            <span class="sc">{{ m.score }}</span>
          </div>
          <div class="s-meta">
            {{ m.specialist.country }}<template v-if="m.specialist.crossBorder.length"> +{{ m.specialist.crossBorder.join(',') }}</template>
            · ★{{ m.specialist.rating }} · {{ m.specialist.cases }} cases · on site in {{ m.specialist.availableInDays }}d
          </div>
          <div class="facts">
            <span>lang {{ (m.factors.language * 100).toFixed(0) }}%</span>
            <span>expertise {{ (m.factors.expertise * 100).toFixed(0) }}%</span>
            <span>avail {{ (m.factors.availability * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>

      <div class="card case">
        <div class="kicker">Live case · {{ kase.id }}</div>
        <h3 class="ct">{{ kase.subject }}</h3>

        <div class="states">
          <span v-for="s in CASE_STATES" :key="s" class="st"
            :class="{ done: CASE_STATES.indexOf(s) < CASE_STATES.indexOf(kase.state), on: s === kase.state }">
            {{ s }}
          </span>
        </div>

        <div class="btns">
          <button class="btn btn-primary sm" type="button" :disabled="!nextState" @click="advance">Advance → {{ nextState || 'closed' }}</button>
          <button class="btn btn-ghost sm" type="button" @click="tryskip">Try to skip a step</button>
          <button class="btn btn-ghost sm" type="button" @click="collect">Seal evidence</button>
          <button class="btn btn-ghost sm" type="button" @click="tamper">Tamper with #0</button>
        </div>

        <div class="chain" :class="{ broken: !chain.valid }">
          <span v-if="chain.valid">🔗 evidence chain intact · {{ kase.evidence.length }} item(s)</span>
          <span v-else>⛓️‍💥 chain broken at item #{{ chain.brokenAt }} — attestation is now impossible until re-collected</span>
        </div>

        <div class="ev" v-for="e in kase.evidence" :key="e.seq">
          <span class="seq">#{{ e.seq }}</span>
          <span class="ty">{{ e.type }}</span>
          <span class="rf">{{ e.ref }}</span>
          <code class="hs">{{ e.hash }}</code>
        </div>

        <div class="log">
          <div v-for="(l, i) in log.slice(0, 6)" :key="i" class="lr" :class="{ bad: !l.ok }">{{ l.msg }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fv { display: flex; flex-direction: column; gap: 16px; }
.card { padding: 18px; }
.head h3 { margin: 4px 0 6px; }
.meta { color: var(--text-dim); font-size: 13px; margin: 0; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 8px; }
.grid { display: grid; grid-template-columns: 5fr 7fr; gap: 14px; align-items: start; }

.f-row { display: flex; gap: 12px; margin-bottom: 12px; }
.f-row label { display: flex; flex-direction: column; gap: 6px; font-size: 11px; color: var(--text-dim); flex: 1; }
select { padding: 7px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 12px; }
.chip { display: inline-block; margin: 0 6px 6px 0; padding: 4px 11px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text-dim); font-size: 11px; cursor: pointer; }
.chip.on { border-color: rgba(124, 92, 255, .5); background: rgba(124, 92, 255, .15); color: #fff; }
.none { font-size: 12px; color: #fbbf24; }

.spec { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; margin-bottom: 8px; }
.s-top { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.sc { font-weight: 800; color: #22d3ee; font-variant-numeric: tabular-nums; }
.s-meta { font-size: 11px; color: var(--text-dim); margin: 3px 0 6px; }
.facts { display: flex; gap: 10px; font-size: 10px; color: var(--text-dim); }

.ct { margin: 0 0 12px; font-size: 15px; }
.states { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.st { font-size: 10px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-dim); }
.st.done { border-color: rgba(52, 211, 153, .4); color: #34d399; }
.st.on { border-color: rgba(124, 92, 255, .55); background: rgba(124, 92, 255, .14); color: #fff; }
.btns { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.btn.sm { padding: 6px 12px; font-size: 11px; }
.btn:disabled { opacity: .4; cursor: default; }

.chain { font-size: 12px; padding: 9px 12px; border-radius: 10px; background: rgba(52, 211, 153, .08); border: 1px solid rgba(52, 211, 153, .3); color: #34d399; margin-bottom: 10px; }
.chain.broken { background: rgba(248, 113, 113, .08); border-color: rgba(248, 113, 113, .35); color: #f87171; }

.ev { display: grid; grid-template-columns: 30px 110px 1fr auto; gap: 8px; font-size: 11px; color: var(--text-dim); padding: 5px 2px; border-bottom: 1px dashed var(--border); align-items: baseline; }
.seq { color: var(--text); font-weight: 700; }
.hs { font-size: 10px; }

.log { margin-top: 12px; }
.lr { font-size: 11px; color: var(--text-dim); padding: 3px 0; }
.lr.bad { color: #f87171; }

@media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } }
</style>
