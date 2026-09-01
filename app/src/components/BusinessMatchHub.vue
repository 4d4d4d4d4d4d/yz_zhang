<script setup>
import { ref, computed } from 'vue'
import { compositeFit } from '../logic/matching.js'

const partners = [
  {
    id: 'lumen', name: 'Lumen Studios', kind: 'Creative agency', city: 'Tokyo, JP',
    years: 9, headcount: '40–80',
    badges: ['KYB verified', 'Identity verified', 'APPI compliant', 'Bank verified'],
    tags: ['Beauty', 'Fashion', 'Premium DTC'],
    bio: 'Tokyo-based creative agency. Built campaigns for Shiseido, Uniqlo, and 3 unicorn DTC brands. Won 2024 Spikes Asia silver.',
    fit: [
      { k: 'Category match', v: 96 }, { k: 'Market match', v: 92 },
      { k: 'Trust signals', v: 94 }, { k: 'Delivery speed', v: 88 }
    ],
    deals: 12, reply: '<2h'
  },
  {
    id: 'aurora', name: 'Aurora Media', kind: 'Media buying', city: 'Singapore, SG',
    years: 6, headcount: '20–50',
    badges: ['KYB verified', 'Identity verified', 'PDPA compliant'],
    tags: ['Beauty', 'Food', 'APAC'],
    bio: 'Media buying specialist for APAC beauty DTC. Managed $40M in 2024 with average 3.6× ROAS.',
    fit: [
      { k: 'Category match', v: 92 }, { k: 'Market match', v: 95 },
      { k: 'Trust signals', v: 88 }, { k: 'Delivery speed', v: 90 }
    ],
    deals: 8, reply: '<4h'
  },
  {
    id: 'northwave', name: 'Northwave Partners', kind: 'Distribution', city: 'São Paulo, BR',
    years: 11, headcount: '80–200',
    badges: ['KYB verified', 'Identity verified', 'LGPD compliant', 'Insurance verified'],
    tags: ['SaaS', 'Tech', 'LATAM'],
    bio: 'B2B SaaS distribution across LATAM. 200+ enterprise relationships in BR, MX, AR.',
    fit: [
      { k: 'Category match', v: 86 }, { k: 'Market match', v: 90 },
      { k: 'Trust signals', v: 92 }, { k: 'Delivery speed', v: 78 }
    ],
    deals: 21, reply: '<8h'
  },
  {
    id: 'cobalt', name: 'Cobalt Legal', kind: 'Compliance partner', city: 'Berlin, DE',
    years: 14, headcount: '10–20',
    badges: ['Bar verified', 'GDPR specialist', 'KYB verified'],
    tags: ['Legal', 'GDPR', 'CCPA', 'APPI'],
    bio: 'Cross-border DPA, terms and IP — beauty, SaaS and consumer tech focus.',
    fit: [
      { k: 'Category match', v: 80 }, { k: 'Market match', v: 88 },
      { k: 'Trust signals', v: 96 }, { k: 'Delivery speed', v: 86 }
    ],
    deals: 34, reply: '<6h'
  }
]

// Spec 54 — the headline score was asserted per partner alongside a fit
// breakdown that disagreed with it: Cobalt's asserted 90 outranked Northwave's
// 88, but their own bars weight out to 87.3 vs 87.5. The score is now the
// weighted composite of those bars, so the two can never contradict.
const ranked = computed(() =>
  partners
    .map(p => {
      const { score, contributions } = compositeFit(p.fit)
      return { ...p, score: Math.round(score * 10) / 10, contributions }
    })
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
)

const active = ref(partners[0].id)
const current = computed(() => ranked.value.find(p => p.id === active.value))
const opener = computed(() => `Hello ${current.value.name.split(' ')[0]} team,\n\nWe are exploring a partnership for our upcoming launch in ${current.value.city.split(',')[1].trim()}. Based on your work with ${current.value.tags[0].toLowerCase()} brands and your ${current.value.years}-year track record, we believe there's a strong fit.\n\nCould we book a 30-minute intro this week to walk through scope, timeline and commercial structure?\n\nBest regards,`)

const inbox = [
  { from: 'Lumen Studios', preview: 'Sharing the Q4 plan and a sample localized hero…', when: '12m', unread: 2 },
  { from: 'Aurora Media',  preview: 'Aligned on the media plan. Bank details attached.', when: '2h',  unread: 0 },
  { from: 'Cobalt Legal',  preview: 'Redline of the DPA — see clauses 4.2 and 7.1.',  when: '1d',  unread: 1 }
]
</script>

<template>
  <div class="biz">
    <div class="card list">
      <div class="lh">
        <h3>Network</h3>
        <span class="meta">{{ ranked.length }} matched · ranked by fit</span>
      </div>
      <button v-for="p in ranked" :key="p.id"
        class="pli" :class="{ on: active === p.id }"
        @click="active = p.id" type="button">
        <div class="logo" :style="{ background: `linear-gradient(135deg, hsl(${p.name.length * 24}, 80%, 65%), hsl(${(p.name.length * 24 + 60) % 360}, 80%, 55%))` }">{{ p.name[0] }}</div>
        <div class="pli-body">
          <div class="pli-top">
            <span class="pn">{{ p.name }}</span>
            <span class="ps">{{ p.score }}</span>
          </div>
          <div class="pk">{{ p.kind }} · {{ p.city }}</div>
        </div>
      </button>
    </div>

    <div class="detail">
      <div class="card profile">
        <div class="prof-head">
          <div class="pavatar" :style="{ background: `linear-gradient(135deg, hsl(${current.name.length * 24}, 80%, 65%), hsl(${(current.name.length * 24 + 60) % 360}, 80%, 55%))` }">{{ current.name[0] }}</div>
          <div class="ph-meta">
            <h3>{{ current.name }}</h3>
            <div class="phk">{{ current.kind }} · {{ current.city }} · {{ current.years }} yrs · {{ current.headcount }} ppl</div>
            <div class="tags">
              <span v-for="t in current.tags" :key="t" class="tag">{{ t }}</span>
            </div>
          </div>
          <div class="trust">
            <div class="trust-num grad-text">{{ current.score }}</div>
            <div class="trust-lbl">Trust score</div>
          </div>
        </div>

        <div class="badges">
          <span v-for="b in current.badges" :key="b" class="badge">✓ {{ b }}</span>
        </div>

        <p class="bio">{{ current.bio }}</p>

        <div class="fit">
          <div class="kicker">Fit breakdown · weighted composite = {{ current.score }}</div>
          <div class="fit-grid">
            <div v-for="c in current.contributions" :key="c.k">
              <div class="frow">
                <span>{{ c.k }} <em class="fw">×{{ c.weight.toFixed(2) }}</em></span>
                <span>{{ c.v }}</span>
              </div>
              <div class="bt"><div class="bf" :style="{ width: c.v + '%' }"></div></div>
              <div class="fcontrib">contributes {{ c.contribution.toFixed(1) }}</div>
            </div>
          </div>
        </div>

        <div class="stats-row">
          <div><div class="sn">{{ current.deals }}</div><div class="sl">Deals closed</div></div>
          <div><div class="sn">{{ current.reply }}</div><div class="sl">Avg. reply</div></div>
          <div><div class="sn">98%</div><div class="sl">On-time delivery</div></div>
        </div>

        <div class="opener">
          <div class="kicker">AI-drafted opener · localized</div>
          <pre>{{ opener }}</pre>
          <div class="actions">
            <button class="btn btn-primary" type="button">Send inquiry →</button>
            <button class="btn btn-ghost" type="button">Schedule intro</button>
            <button class="btn btn-ghost" type="button">Translate · 日本語</button>
          </div>
        </div>
      </div>

      <div class="card inbox">
        <div class="lh">
          <h3>Inbox</h3>
          <span class="meta">{{ inbox.reduce((s, i) => s + i.unread, 0) }} unread</span>
        </div>
        <div v-for="m in inbox" :key="m.from" class="thread">
          <div class="th-row">
            <span class="th-from">{{ m.from }}</span>
            <span class="th-when">{{ m.when }}</span>
          </div>
          <div class="th-prev">{{ m.preview }}</div>
          <span v-if="m.unread" class="dot">{{ m.unread }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.biz { display: grid; grid-template-columns: 280px 1fr; gap: 20px; align-items: flex-start; }
.list { padding: 16px; }
.lh { display: flex; justify-content: space-between; align-items: baseline; padding: 0 4px 12px; }
.meta { color: var(--text-dim); font-size: 12px; }
.pli { display: flex; gap: 12px; padding: 12px; width: 100%; background: transparent; border: 1px solid transparent; border-radius: 10px; cursor: pointer; color: var(--text); text-align: left; align-items: center; }
.pli:hover { background: var(--surface); }
.pli.on { background: rgba(124, 92, 255, .12); border-color: rgba(124, 92, 255, .35); }
.logo { width: 36px; height: 36px; border-radius: 8px; display: grid; place-items: center; font-weight: 800; color: #0a0a0f; flex-shrink: 0; }
.pli-body { flex: 1; min-width: 0; }
.pli-top { display: flex; justify-content: space-between; gap: 8px; }
.pn { font-weight: 600; font-size: 14px; }
.ps { font-size: 13px; color: var(--primary-2); font-weight: 700; }
.pk { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

.detail { display: flex; flex-direction: column; gap: 16px; }
.profile { padding: 24px; }
.prof-head { display: grid; grid-template-columns: auto 1fr auto; gap: 18px; align-items: center; margin-bottom: 18px; }
.pavatar { width: 64px; height: 64px; border-radius: 14px; display: grid; place-items: center; font-size: 26px; font-weight: 800; color: #0a0a0f; }
.phk { color: var(--text-dim); font-size: 13px; margin: 4px 0 10px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
.tag { padding: 4px 10px; border-radius: 6px; background: var(--surface-2); font-size: 11px; color: var(--text); border: 1px solid var(--border); }
.trust { text-align: right; }
.trust-num { font-size: 36px; font-weight: 800; line-height: 1; }
.trust-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 2px; }

.badges { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.badge { padding: 6px 10px; border-radius: 999px; font-size: 11px; background: rgba(52, 211, 153, .12); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, .3); }

.bio { color: var(--text); margin: 0 0 20px; line-height: 1.6; }

.fit { margin-bottom: 20px; }
.kicker { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 10px; }
.fit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 24px; }
.frow { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; color: var(--text-dim); }
.fw { font-style: normal; font-size: 10px; opacity: .7; }
.fcontrib { font-size: 10px; color: var(--text-dim); margin-top: 3px; font-variant-numeric: tabular-nums; }
.bt { height: 4px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.bf { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); }

.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 16px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); margin-bottom: 20px; }
.sn { font-size: 20px; font-weight: 800; font-variant-numeric: tabular-nums; }
.sl { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }

.opener pre { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; color: var(--text); font-family: inherit; font-size: 13px; line-height: 1.55; margin: 10px 0 14px; white-space: pre-wrap; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }

.inbox { padding: 20px; }
.thread { padding: 12px 14px; border-radius: 10px; cursor: pointer; position: relative; }
.thread:hover { background: var(--surface); }
.th-row { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
.th-from { font-weight: 600; }
.th-when { color: var(--text-dim); font-size: 12px; }
.th-prev { color: var(--text-dim); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dot { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: var(--primary); color: #fff; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 999px; }

@media (max-width: 900px) {
  .biz { grid-template-columns: 1fr; }
  .prof-head { grid-template-columns: auto 1fr; }
  .trust { grid-column: 1 / -1; text-align: left; display: flex; align-items: center; gap: 16px; }
  .fit-grid { grid-template-columns: 1fr; }
}
</style>
