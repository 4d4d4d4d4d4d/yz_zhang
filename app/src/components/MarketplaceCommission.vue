<script setup>
import { computed } from 'vue'

const tiers = [
  { name: 'Platinum', rate: 8,  cap: '∞',     partners: 8,  gmv: 1840000, color: '#7c5cff' },
  { name: 'Gold',     rate: 12, cap: '$500k', partners: 22, gmv: 1240000, color: '#fbbf24' },
  { name: 'Silver',   rate: 16, cap: '$200k', partners: 48, gmv: 680000,  color: '#22d3ee' },
  { name: 'Standard', rate: 20, cap: '$50k',  partners: 142, gmv: 384000, color: '#94a3b8' }
]

const earners = [
  { name: 'Lumen Studios',      tier: 'Platinum', gmv: 384000, comm: 30720, payout: 'Dec 15' },
  { name: 'Aurora Media',       tier: 'Platinum', gmv: 268000, comm: 21440, payout: 'Dec 15' },
  { name: 'Northwave Partners', tier: 'Gold',     gmv: 412000, comm: 49440, payout: 'Dec 15' },
  { name: 'Mizu Logistics',     tier: 'Gold',     gmv: 196000, comm: 23520, payout: 'Dec 18' },
  { name: 'Verda Commerce',     tier: 'Silver',   gmv:  84000, comm: 13440, payout: 'Dec 18' },
  { name: 'Helio Network',      tier: 'Standard', gmv:  28000, comm:  5600, payout: 'Dec 22' }
]

const commByTier = computed(() => tiers.map(t => ({ ...t, comm: Math.round(t.gmv * t.rate / 100) })))
const totalGMV = computed(() => tiers.reduce((s, t) => s + t.gmv, 0))
const totalComm = computed(() => commByTier.value.reduce((s, t) => s + t.comm, 0))
const totalPartners = computed(() => tiers.reduce((s, t) => s + t.partners, 0))
const blendedRate = computed(() => ((totalComm.value / totalGMV.value) * 100).toFixed(2))

const payoutQueue = [
  { date: 'Dec 15', count: 18, amount: 184000 },
  { date: 'Dec 18', count: 24, amount: 142000 },
  { date: 'Dec 22', count: 38, amount: 96000 },
  { date: 'Jan 02', count: 64, amount: 142000 }
]
</script>

<template>
  <div class="mc">
    <div class="card head">
      <div>
        <div class="kicker">Marketplace economics · take-rate</div>
        <h3>${{ Math.round(totalGMV / 1000).toLocaleString() }}k GMV · ${{ Math.round(totalComm / 1000).toLocaleString() }}k commission this month</h3>
        <p class="meta">Blended take-rate {{ blendedRate }}% · {{ totalPartners }} active partners across 4 tiers · payouts run on the 15th, 18th and 22nd.</p>
      </div>
    </div>

    <div class="kpi-row">
      <div class="card kpi">
        <div class="kk">GMV</div>
        <div class="kv grad-text">${{ (totalGMV / 1e6).toFixed(2) }}M</div>
        <div class="kd up">▲ +18% MoM</div>
      </div>
      <div class="card kpi">
        <div class="kk">Commission</div>
        <div class="kv">${{ Math.round(totalComm / 1000).toLocaleString() }}k</div>
        <div class="kd up">▲ +12% MoM</div>
      </div>
      <div class="card kpi">
        <div class="kk">Blended rate</div>
        <div class="kv">{{ blendedRate }}%</div>
        <div class="kd dimc">target 12.5%</div>
      </div>
      <div class="card kpi">
        <div class="kk">Active partners</div>
        <div class="kv">{{ totalPartners }}</div>
        <div class="kd up">+24 new</div>
      </div>
    </div>

    <div class="card">
      <h3>Tier waterfall</h3>
      <p class="meta">Higher-tier partners earn the platform less per dollar but generate more volume.</p>
      <div class="tiers">
        <div v-for="t in commByTier" :key="t.name" class="tr">
          <div class="tr-head">
            <span class="tr-name"><span class="tr-dot" :style="{ background: t.color }"></span>{{ t.name }}</span>
            <span class="tr-meta">{{ t.rate }}% · cap {{ t.cap }} · {{ t.partners }} partners</span>
          </div>
          <div class="tr-bar">
            <div class="tr-gmv" :style="{ width: (t.gmv / totalGMV * 100) + '%', background: t.color }">
              <span>${{ Math.round(t.gmv / 1000) }}k GMV</span>
            </div>
          </div>
          <div class="tr-bar small">
            <div class="tr-comm" :style="{ width: (t.comm / totalGMV * 100 * 4) + '%', background: t.color, opacity: .65 }">
              <span>${{ Math.round(t.comm / 1000) }}k commission</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h3>Top partners by commission</h3>
        <table class="te">
          <thead>
            <tr><th>Partner</th><th>Tier</th><th class="num">GMV</th><th class="num">Commission</th><th>Payout</th></tr>
          </thead>
          <tbody>
            <tr v-for="e in earners" :key="e.name">
              <td><strong>{{ e.name }}</strong></td>
              <td><span class="tier" :class="e.tier.toLowerCase()">{{ e.tier }}</span></td>
              <td class="num">${{ Math.round(e.gmv / 1000) }}k</td>
              <td class="num"><strong>${{ Math.round(e.comm / 1000) }}k</strong></td>
              <td class="dimc">{{ e.payout }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>Upcoming payouts</h3>
        <div class="po">
          <div v-for="p in payoutQueue" :key="p.date" class="po-row">
            <div class="po-date">{{ p.date }}</div>
            <div class="po-meta">{{ p.count }} payouts</div>
            <div class="po-amt">${{ Math.round(p.amount / 1000) }}k</div>
          </div>
        </div>
        <div class="po-note">
          <span class="ai-tag">AI</span>
          One partner is approaching their tier cap — promotion to Gold would <strong>save 4pt</strong> in commission next month.
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mc { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }

.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi { padding: 16px 18px; }
.kk { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.kv { font-size: 24px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; margin: 8px 0 4px; }
.kd { font-size: 11px; }
.kd.up { color: var(--success); }
.kd.dimc { color: var(--text-dim); }

.tiers { display: flex; flex-direction: column; gap: 14px; margin-top: 14px; }
.tr { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.tr-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.tr-name { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13px; }
.tr-dot { width: 10px; height: 10px; border-radius: 50%; }
.tr-meta { font-size: 11px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.tr-bar { height: 22px; border-radius: 6px; overflow: hidden; background: var(--surface-2); margin-bottom: 6px; }
.tr-bar.small { height: 14px; }
.tr-gmv, .tr-comm { height: 100%; display: flex; align-items: center; padding: 0 8px; color: #fff; font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums; min-width: 70px; }

.row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.te { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 12px; }
.te th { text-align: left; padding: 8px 10px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.te th.num { text-align: right; }
.te td { padding: 10px; border-bottom: 1px dashed var(--border); }
.te td.num { text-align: right; font-variant-numeric: tabular-nums; }
.te td.dimc { color: var(--text-dim); }

.tier { font-size: 10px; padding: 2px 8px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.tier.platinum { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.tier.gold { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.tier.silver { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.tier.standard { background: var(--surface-2); color: var(--text-dim); }

.po { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.po-row { display: grid; grid-template-columns: 70px 1fr auto; gap: 12px; align-items: center; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
.po-date { font-weight: 700; font-size: 13px; }
.po-meta { font-size: 11px; color: var(--text-dim); }
.po-amt { font-weight: 800; font-variant-numeric: tabular-nums; font-size: 14px; }

.po-note { display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; background: rgba(124, 92, 255, .08); border: 1px solid rgba(124, 92, 255, .25); border-radius: 10px; font-size: 12px; color: var(--text-dim); margin-top: 14px; line-height: 1.5; }
.po-note strong { color: var(--text); }
.ai-tag { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 800; letter-spacing: .05em; flex-shrink: 0; }

@media (max-width: 1024px) {
  .kpi-row { grid-template-columns: 1fr 1fr; }
  .row { grid-template-columns: 1fr; }
}
</style>
