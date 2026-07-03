<script setup>
import { ref, computed } from 'vue'
import { trustScore } from '../logic/showcase.js'
import { createCase, advanceCase, addEvidence, verifyChain, CASE_STATES } from '../logic/fieldVerify.js'
import { assessCampaign, dueDiligence } from '../logic/riskLegal.js'
import { evaluateTerms } from '../logic/negotiation.js'
import { dealReadiness, STAGES } from '../logic/pipeline.js'

// --- interactive deal state -------------------------------------------------
const reelEvidence = ref({ provenance: true, metricsVerified: false, clientAttested: false, complianceGate: true })
const reelCount = ref(1)

const caseProgress = ref(0) // index into CASE_STATES
const chainIntact = ref(true)

const campaignAttrs = ref({ consent: true, dpa: true, localization: true, ageGate: true, adDisclosure: true, provenance: true })
const partnerChecks = ref({ kyb: true, sanctions: true, references: true, financials: false, dataProcessing: true })

const proposal = ref({ discount: 15, paymentDays: 45, liability: 'capped-1x' })
const PLAYBOOK = { rules: [
  { term: 'discount', op: 'max', value: 20, severity: 'block', label: 'Max discount %' },
  { term: 'paymentDays', op: 'max', value: 60, severity: 'warn', label: 'Payment terms' },
  { term: 'liability', op: 'required', value: 'capped-1x', severity: 'block', label: 'Liability cap' }
] }

// --- domain engines feed the pipeline ----------------------------------------
const reels = computed(() => Array.from({ length: reelCount.value }, () => trustScore(reelEvidence.value)))

const fieldCase = computed(() => {
  const k = createCase({ id: 'FV-DEMO', country: 'JP', subject: 'demo' })
  for (let i = 1; i <= caseProgress.value; i++) {
    if (CASE_STATES[i] === 'evidence-collected') {
      addEvidence(k, { type: 'site-photo', ref: 'p1' }, 1000)
      addEvidence(k, { type: 'license-scan', ref: 'l1' }, 2000)
    }
    advanceCase(k, CASE_STATES[i])
  }
  if (!chainIntact.value && k.evidence.length) k.evidence[0].ref = 'tampered'
  return { state: k.state, chainValid: verifyChain(k).valid }
})

const compliance = computed(() => assessCampaign({ markets: ['JP', 'EU'], attributes: campaignAttrs.value }))
const diligence = computed(() => dueDiligence({ checks: partnerChecks.value }))
const terms = computed(() => evaluateTerms(proposal.value, PLAYBOOK))

const readiness = computed(() => dealReadiness({
  reels: reels.value, fieldCase: fieldCase.value,
  compliance: compliance.value, diligence: diligence.value, terms: terms.value
}))

const STAGE_LABEL = { evidence: 'Evidence', verification: 'Verification', compliance: 'Compliance', commercial: 'Commercial' }
const gaugeColor = computed(() =>
  readiness.value.hardFail ? '#f87171' : readiness.value.readyToSign ? '#34d399' : '#7c5cff')
</script>

<template>
  <div class="tp">
    <div class="card head">
      <div>
        <div class="kicker">Trust pipeline · evidence → signature</div>
        <h3>How far is this deal from a signature?</h3>
        <p class="meta">Live composition of showcase trust, field verification, compliance gates and playbook terms into one deal-readiness score. Toggle the inputs — watch the gates.</p>
      </div>
      <div class="gauge" :style="{ '--c': gaugeColor }">
        <div class="g-score">{{ readiness.score }}</div>
        <div class="g-label">{{ readiness.readyToSign ? 'READY TO SIGN' : readiness.hardFail ? 'HARD FAIL' : 'stage: ' + readiness.stage }}</div>
      </div>
    </div>

    <div class="stages card">
      <div v-for="st in STAGES" :key="st" class="stg"
        :class="{ full: readiness.credits[st] === 1, half: readiness.credits[st] === 0.5 }">
        <div class="s-name">{{ STAGE_LABEL[st] }}</div>
        <div class="s-bar"><div class="s-fill" :style="{ width: readiness.credits[st] * 100 + '%' }"></div></div>
        <div class="s-pts">{{ readiness.credits[st] * 25 }}/25</div>
      </div>
    </div>

    <div v-if="readiness.blockers.length" class="card blockers">
      <div class="kicker">What's blocking</div>
      <div v-for="b in readiness.blockers" :key="b.stage" class="blk" :class="b.severity">
        <b>{{ STAGE_LABEL[b.stage] }}</b> {{ b.action }}
      </div>
    </div>
    <div v-else class="card ready">✓ All four gates at full credit — route to e-sign in the Deal Room.</div>

    <div class="grid">
      <div class="card ctl">
        <div class="kicker">1 · Showcase evidence</div>
        <label><input type="checkbox" v-model="reelEvidence.metricsVerified" /> metrics verified via platform API</label>
        <label><input type="checkbox" v-model="reelEvidence.clientAttested" /> client attested the case study</label>
        <label>reels linked <input type="range" min="0" max="4" v-model.number="reelCount" /> {{ reelCount }}</label>
        <p class="sub">avg trust {{ reels.length ? Math.round(reels.reduce((s, r) => s + r.score, 0) / reels.length) : 0 }}</p>
      </div>

      <div class="card ctl">
        <div class="kicker">2 · Field verification</div>
        <label>case progress <input type="range" min="0" :max="CASE_STATES.length - 1" v-model.number="caseProgress" /></label>
        <p class="sub">{{ fieldCase.state }}</p>
        <label><input type="checkbox" v-model="chainIntact" /> evidence chain intact</label>
        <p v-if="!fieldCase.chainValid" class="warn">chain broken → hard fail</p>
      </div>

      <div class="card ctl">
        <div class="kicker">3 · Compliance</div>
        <label><input type="checkbox" v-model="campaignAttrs.consent" /> consent framework (blocking)</label>
        <label><input type="checkbox" v-model="campaignAttrs.ageGate" /> age gate (warn)</label>
        <label><input type="checkbox" v-model="partnerChecks.sanctions" /> sanctions screening (blocking)</label>
        <label><input type="checkbox" v-model="partnerChecks.financials" /> partner financials (warn)</label>
        <p class="sub">campaign: {{ compliance.gate }} · partner: {{ diligence.gate }}</p>
      </div>

      <div class="card ctl">
        <div class="kicker">4 · Commercial terms</div>
        <label>discount % <input type="range" min="0" max="40" v-model.number="proposal.discount" /> {{ proposal.discount }}</label>
        <label>payment days <input type="range" min="15" max="120" step="15" v-model.number="proposal.paymentDays" /> {{ proposal.paymentDays }}</label>
        <label><input type="checkbox" :checked="!!proposal.liability" @change="proposal.liability = $event.target.checked ? 'capped-1x' : null" /> liability cap present</label>
        <p class="sub">verdict: {{ terms.verdict }}<template v-if="terms.findings.length"> · {{ terms.findings.length }} finding(s)</template></p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tp { display: flex; flex-direction: column; gap: 14px; }
.card { padding: 18px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.head h3 { margin: 4px 0 6px; }
.meta { color: var(--text-dim); font-size: 13px; margin: 0; max-width: 560px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 8px; }

.gauge { min-width: 150px; text-align: center; padding: 14px 20px; border-radius: 14px; border: 2px solid var(--c); }
.g-score { font-size: 40px; font-weight: 800; color: var(--c); font-variant-numeric: tabular-nums; line-height: 1; }
.g-label { font-size: 10px; text-transform: uppercase; letter-spacing: .1em; color: var(--text-dim); margin-top: 6px; }

.stages { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.stg { display: flex; flex-direction: column; gap: 6px; }
.s-name { font-size: 12px; font-weight: 700; color: var(--text-dim); }
.stg.full .s-name { color: #34d399; }
.stg.half .s-name { color: #fbbf24; }
.s-bar { height: 8px; border-radius: 999px; background: var(--surface-2); overflow: hidden; }
.s-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); transition: width .25s; }
.stg.full .s-fill { background: #34d399; }
.s-pts { font-size: 10px; color: var(--text-dim); font-variant-numeric: tabular-nums; }

.blockers .blk { font-size: 12px; padding: 8px 12px; border-radius: 10px; border: 1px solid rgba(251, 191, 36, .35); background: rgba(251, 191, 36, .07); color: var(--text-dim); margin-top: 6px; }
.blockers .blk.zero { border-color: rgba(248, 113, 113, .4); background: rgba(248, 113, 113, .07); }
.blockers .blk b { color: var(--text); margin-right: 8px; }
.ready { color: #34d399; font-size: 13px; border-color: rgba(52, 211, 153, .35); }

.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.ctl { padding: 14px; }
.ctl label { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--text-dim); padding: 5px 0; flex-wrap: wrap; }
.ctl input[type="range"] { flex: 1; min-width: 60px; }
.sub { font-size: 11px; color: var(--text); margin: 8px 0 0; }
.warn { font-size: 11px; color: #f87171; margin: 4px 0 0; }

@media (max-width: 1000px) { .grid, .stages { grid-template-columns: repeat(2, 1fr); } }
</style>
