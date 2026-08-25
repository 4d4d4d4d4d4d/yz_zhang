<script setup>
import { ref, computed } from 'vue'
import { rankOpportunities, scoreBreakdown } from '../logic/expansion.js'

const accounts = ref([
  {
    id: 'lumi', name: 'Lumi DTC', plan: 'Enterprise', mrr: 9800, score: 92, type: 'expansion',
    signals: [
      { tag: 'usage',   text: 'API calls at 95% of allowance · 2 months in a row', strength: 'high' },
      { tag: 'feature', text: 'Brand kits underutilized (3 of 12 seats activated)', strength: 'med' },
      { tag: 'intent',  text: 'Visited /pricing/scale 3× this week from corp IP',   strength: 'high' }
    ],
    play: 'Propose Scale tier upgrade + 12-month commit',
    upside: 4200,
    email: 'Hi Mei,\n\nLooking at your last 60 days: 95% of API allowance used, render queue saturated on launches, and your team is exploring Scale features.\n\nA Scale upgrade adds unlimited renders + API and saves $420/mo on overages. Want a 20-min review on whether it pays back this quarter?\n\n— Akiko'
  },
  {
    id: 'kaito', name: 'Kaito Beauty', plan: 'Growth', mrr: 2400, score: 84, type: 'upsell',
    signals: [
      { tag: 'usage',  text: 'Render volume +180% QoQ', strength: 'high' },
      { tag: 'feature',text: 'No multi-market rendering enabled · clearly localizing manually', strength: 'med' },
      { tag: 'team',   text: 'Added 4 new seats in the last 2 weeks',  strength: 'med' }
    ],
    play: 'Bundle multi-market add-on + team training',
    upside: 1600,
    email: 'Hi Risa,\n\nNoticed Kaito has added 4 new seats and your render volume nearly tripled this quarter. Most teams at this scale switch on multi-market rendering — it would cut your localization time by ~70%.\n\nHappy to set up a 1-hour onboarding for the whole team this week.\n\n— Hana'
  },
  {
    id: 'northwave', name: 'Northwave Partners', plan: 'Enterprise', mrr: 12400, score: 76, type: 'expansion',
    signals: [
      { tag: 'pilot',  text: 'LATAM expansion pilot ending Dec 15',     strength: 'high' },
      { tag: 'health', text: 'NPS 9 last quarter · champion is engaged', strength: 'high' },
      { tag: 'usage',  text: 'API utilization 64%, room to grow',       strength: 'low' }
    ],
    play: 'Renewal + LATAM expansion as add-on',
    upside: 6800,
    email: 'Hi Rafael,\n\nWith the LATAM pilot wrapping up Dec 15, this is a great moment to lock the renewal and roll the LATAM expansion into the same contract — saves admin overhead and unlocks bundle pricing.\n\nWant to walk through the proposal Thursday?\n\n— Akiko'
  },
  {
    id: 'aurora', name: 'Aurora Media', plan: 'Enterprise', mrr: 6200, score: 71, type: 'upsell',
    signals: [
      { tag: 'feature', text: 'Heavy use of A/B testing — not on advanced experiments plan', strength: 'med' },
      { tag: 'client',  text: 'Manages 12 sub-clients · agency add-on fits',                  strength: 'high' }
    ],
    play: 'Agency add-on (sub-client billing + experiments)',
    upside: 2400,
    email: 'Hi Jun,\n\nYou\'re running 12 active sub-clients on Aurora\'s instance and managing them as one workspace. The Agency add-on splits billing per client, gives them embeddable dashboards, and unlocks the full experiment manager.\n\n— Kenji'
  },
  {
    id: 'cobalt', name: 'Cobalt Legal', plan: 'Growth', mrr: 1800, score: 62, type: 'upsell',
    signals: [
      { tag: 'feature', text: 'Tried clause library 8× in last 14 days', strength: 'med' },
      { tag: 'integration', text: 'Asked about SSO via support',         strength: 'high' }
    ],
    play: 'Scale tier (SSO + clause library quotas)',
    upside: 800,
    email: 'Hi Anya,\n\nYour team has been exploring the clause library — Scale tier removes the cap and brings SSO (which support flagged as a recurring ask).\n\nReady to walk through tomorrow?\n\n— Diego'
  }
])

const selected = ref('lumi')
const filter = ref('all')
const filters = ['all', 'expansion', 'upsell']

// Spec 53 — the score was a hardcoded number per account while the signals
// that should produce it sat unused. It is now derived, and accounts are
// ranked by expected value (propensity × upside) rather than raw upside.
const ranked = computed(() => rankOpportunities(accounts.value))
const filtered = computed(() => filter.value === 'all' ? ranked.value : ranked.value.filter(a => a.type === filter.value))
const cur = computed(() => ranked.value.find(a => a.id === selected.value))
const curBreakdown = computed(() => scoreBreakdown(cur.value?.signals))

const summary = computed(() => ({
  count: ranked.value.length,
  upside: ranked.value.reduce((s, a) => s + a.upside, 0),
  weighted: ranked.value.reduce((s, a) => s + a.expectedValue, 0),
  avgScore: ranked.value.length
    ? Math.round(ranked.value.reduce((s, a) => s + a.score, 0) / ranked.value.length)
    : 0
}))
</script>

<template>
  <div class="up">
    <div class="card head">
      <div>
        <div class="kicker">Expansion engine · AI-scored</div>
        <h3>{{ summary.count }} accounts with expansion signal · +${{ summary.upside.toLocaleString() }} MRR upside</h3>
        <p class="meta">
          Score is <strong>evidence coverage</strong>: each observed signal weighted by how predictive it is,
          against the full signal set — so partial evidence scores partially.
          Ranked by expected value (score × upside), not headline upside:
          <strong class="grad-text">${{ Math.round(summary.weighted).toLocaleString() }}</strong> weighted pipeline.
        </p>
      </div>
      <div class="filt">
        <button v-for="f in filters" :key="f" :class="{ on: filter === f }" @click="filter = f" type="button">{{ f }}</button>
      </div>
    </div>

    <div class="grid">
      <div class="card list">
        <div v-for="a in filtered" :key="a.id"
          class="ac" :class="{ on: selected === a.id }"
          @click="selected = a.id">
          <div class="ac-head">
            <span class="ac-name">{{ a.name }}</span>
            <span class="ac-score" :class="a.score >= 45 ? 'high' : a.score >= 25 ? 'med' : 'low'">{{ a.score }}</span>
          </div>
          <div class="ac-meta">
            <span class="pl-pill">{{ a.plan }}</span>
            <span class="ty-pill" :class="a.type">{{ a.type }}</span>
            <span class="ac-mrr">${{ a.mrr.toLocaleString() }} MRR</span>
          </div>
          <div class="ac-upside">
            <span>${{ Math.round(a.expectedValue).toLocaleString() }}</span>
            <span class="dimc-i">expected · of ${{ a.upside.toLocaleString() }} upside</span>
          </div>
        </div>
      </div>

      <div class="card detail">
        <div class="d-head">
          <div>
            <div class="kicker">{{ cur.type }} · score {{ cur.score }}</div>
            <h3>{{ cur.name }} · {{ cur.plan }}</h3>
            <p class="meta">${{ cur.mrr.toLocaleString() }} MRR today → projected <strong class="grad-text">${{ (cur.mrr + cur.upside).toLocaleString() }}</strong> after play</p>
          </div>
          <div class="d-actions">
            <button class="btn btn-ghost sm" type="button">Snooze 30d</button>
            <button class="btn btn-primary sm" type="button">Launch play →</button>
          </div>
        </div>

        <div class="kicker">Signals · why this scored {{ cur.score }}</div>
        <div class="signals">
          <div v-for="(s, i) in cur.signals" :key="i" class="sg">
            <span class="sg-tag" :class="s.tag">{{ s.tag }}</span>
            <span class="sg-text">{{ s.text }}</span>
            <span class="sg-str" :class="s.strength">{{ s.strength }}</span>
          </div>
        </div>

        <div class="kicker">Score contribution</div>
        <div class="contrib">
          <div v-for="c in curBreakdown" :key="c.tag" class="cb">
            <span class="cb-tag">{{ c.tag }}</span>
            <div class="cb-track"><div class="cb-fill" :style="{ width: (c.contribution / 25 * 100) + '%' }"></div></div>
            <span class="cb-pts">{{ c.contribution.toFixed(1) }} pts</span>
          </div>
          <p class="cb-note">
            Expected value <strong>${{ Math.round(cur.expectedValue).toLocaleString() }}</strong>
            = {{ cur.score }}% × ${{ cur.upside.toLocaleString() }} upside
          </p>
        </div>

        <div class="kicker">Recommended play</div>
        <div class="play">
          <span class="ai-tag">AI</span>
          <strong>{{ cur.play }}</strong>
        </div>

        <div class="kicker">Pre-drafted outreach</div>
        <pre>{{ cur.email }}</pre>
        <div class="m-actions">
          <button class="btn btn-primary sm" type="button">Send via Outreach sequence</button>
          <button class="btn btn-ghost sm" type="button">Regenerate</button>
          <button class="btn btn-ghost sm" type="button">Translate</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.up { display: flex; flex-direction: column; gap: 16px; }
.contrib { display: flex; flex-direction: column; gap: 7px; margin-bottom: 16px; }
.cb { display: grid; grid-template-columns: 92px 1fr 66px; gap: 10px; align-items: center; font-size: 11px; }
.cb-tag { color: var(--text-dim); text-transform: capitalize; }
.cb-track { height: 7px; border-radius: 999px; background: var(--surface-2); overflow: hidden; }
.cb-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }
.cb-pts { text-align: right; font-variant-numeric: tabular-nums; color: var(--text); }
.cb-note { font-size: 11px; color: var(--text-dim); margin: 8px 0 0; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-top: 14px; margin-bottom: 8px; font-weight: 700; }
.kicker:first-child { margin-top: 0; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.dimc-i { color: var(--text-dim); font-size: 11px; }

.filt { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); gap: 2px; }
.filt button { padding: 5px 14px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 12px; text-transform: capitalize; }
.filt button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.grid { display: grid; grid-template-columns: 1fr 1.6fr; gap: 16px; align-items: flex-start; }

.list { padding: 14px; display: flex; flex-direction: column; gap: 6px; }
.ac { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); cursor: pointer; }
.ac:hover { border-color: var(--primary); }
.ac.on { border-color: var(--primary); background: rgba(124, 92, 255, .1); }
.ac-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.ac-name { font-weight: 700; font-size: 14px; }
.ac-score { font-size: 14px; font-weight: 800; padding: 3px 8px; border-radius: 5px; font-variant-numeric: tabular-nums; }
.ac-score.high { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.ac-score.med { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.ac-score.low { background: rgba(96, 165, 250, .15); color: #93c5fd; }
.ac-meta { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; font-size: 11px; margin-bottom: 6px; }
.pl-pill { padding: 2px 7px; border-radius: 4px; background: rgba(124, 92, 255, .15); color: #c4b5fd; font-weight: 700; }
.ty-pill { padding: 2px 7px; border-radius: 4px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; font-size: 9px; }
.ty-pill.expansion { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.ty-pill.upsell { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.ac-mrr { color: var(--text-dim); font-variant-numeric: tabular-nums; margin-left: auto; }
.ac-upside { font-size: 12px; font-weight: 700; color: var(--success); }
.ac-upside .dimc-i { color: var(--text-dim); font-weight: 500; margin-left: 4px; }

.detail { padding: 20px; }
.d-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }
.d-actions { display: flex; gap: 8px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.signals { display: flex; flex-direction: column; gap: 8px; }
.sg { display: grid; grid-template-columns: 90px 1fr 80px; gap: 10px; align-items: center; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); font-size: 13px; }
.sg-tag { font-size: 10px; padding: 3px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; text-align: center; }
.sg-tag.usage { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.sg-tag.feature { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.sg-tag.intent { background: rgba(255, 122, 217, .15); color: #f5d0fe; }
.sg-tag.health { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.sg-tag.team { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.sg-tag.pilot { background: rgba(96, 165, 250, .15); color: #93c5fd; }
.sg-tag.client { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.sg-tag.integration { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.sg-str { text-align: right; font-size: 10px; padding: 2px 7px; border-radius: 4px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.sg-str.high { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.sg-str.med { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.sg-str.low { background: var(--surface-2); color: var(--text-dim); }

.play { display: flex; gap: 10px; align-items: center; padding: 12px 14px; background: rgba(124, 92, 255, .08); border: 1px solid rgba(124, 92, 255, .25); border-radius: 10px; font-size: 14px; }
.play strong { color: var(--text); font-weight: 600; }
.ai-tag { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 800; letter-spacing: .05em; }

.detail pre { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; color: var(--text); font-family: inherit; font-size: 13px; line-height: 1.6; margin: 0 0 14px; white-space: pre-wrap; }
.m-actions { display: flex; gap: 8px; flex-wrap: wrap; }

@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; }
  .sg { grid-template-columns: 80px 1fr; }
  .sg-str { display: none; }
}
</style>
