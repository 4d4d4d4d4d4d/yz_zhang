<script setup>
import { ref } from 'vue'

const account = {
  name: 'Lumen Studios',
  domain: 'lumen-studios.jp',
  hq: 'Tokyo, JP',
  size: '40–80',
  founded: 2016,
  icp: 92,
  arr_band: '$8–12M',
  tech: ['Shopify Plus', 'Klaviyo', 'Mixpanel', 'Notion'],
  funding: 'Series A · $14M'
}

const intent = [
  { sig: 'Surge in branded search for "DTC localization Japan"', src: 'Bombora', when: '2h',  weight: 84 },
  { sig: 'Visited /pricing 3× in 6 days from corporate IP',       src: 'AdForge',  when: '5h',  weight: 76 },
  { sig: '2 new openings: Growth Marketing Lead, Localization PM', src: 'LinkedIn', when: '1d',  weight: 72 },
  { sig: 'Trademark filing for new product line in Japan',        src: 'JPO',      when: '2d',  weight: 68 },
  { sig: 'CEO speaking at Tokyo DTC Summit next month',           src: 'News',     when: '3d',  weight: 58 }
]

const news = [
  { t: 'Lumen Studios raises $14M Series A led by Mistletoe', when: 'Nov 24', src: 'TechCrunch' },
  { t: '"Why Japanese brands need a localization-first ad stack" — CEO op-ed', when: 'Nov 18', src: 'Nikkei XTECH' },
  { t: 'Partnership announced with Rakuten Beauty division',  when: 'Oct 30', src: 'PR Times' }
]

const org = [
  { id: 'ceo',   name: 'Hiro Yamazaki', role: 'CEO / Founder',       persona: 'champion',  intent: 'high',  warm: 1 },
  { id: 'coo',   name: 'Sora Kimura',   role: 'COO',                 persona: 'decision',  intent: 'med',   warm: 0 },
  { id: 'cmo',   name: 'Mei Tanaka',    role: 'CMO',                 persona: 'economic',  intent: 'high',  warm: 1 },
  { id: 'head',  name: 'Kenta Sato',    role: 'Head of Performance', persona: 'user',      intent: 'high',  warm: 2 },
  { id: 'legal', name: 'Akira Mori',    role: 'GC (interim)',        persona: 'blocker',   intent: 'low',   warm: 0 }
]

const mutuals = [
  { name: 'Yuki Hayashi', via: 'Hiro Yamazaki', strength: 'strong', context: 'Worked together at Mercari' },
  { name: 'Daniel Park',  via: 'Mei Tanaka',     strength: 'medium', context: 'Both on Tokyo DTC Slack' }
]

const selected = ref('cmo')

function persColor(p) {
  return { champion: '#34d399', decision: '#7c5cff', economic: '#22d3ee', user: '#fcd34d', blocker: '#f87171' }[p]
}
</script>

<template>
  <div class="ai">
    <div class="card head">
      <div class="ah-left">
        <div class="logo">L</div>
        <div>
          <h3>{{ account.name }}</h3>
          <div class="dm">{{ account.domain }} · {{ account.hq }} · {{ account.size }} ppl · founded {{ account.founded }}</div>
          <div class="dm">{{ account.funding }} · ARR band {{ account.arr_band }}</div>
        </div>
      </div>
      <div class="ah-right">
        <div class="icp">
          <div class="icp-num grad-text">{{ account.icp }}</div>
          <div class="icp-lbl">ICP score</div>
        </div>
        <button class="btn btn-primary sm" type="button">Start cadence</button>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <div class="hh">
          <h3>Intent signals</h3>
          <span class="meta">Live · last 7 days</span>
        </div>
        <div class="signals">
          <div v-for="(s, i) in intent" :key="i" class="sg">
            <div class="sg-row">
              <span class="sg-text">{{ s.sig }}</span>
              <span class="sg-weight" :class="s.weight >= 80 ? 'high' : s.weight >= 65 ? 'med' : 'low'">{{ s.weight }}</span>
            </div>
            <div class="sg-foot"><span>{{ s.src }}</span><span>·</span><span>{{ s.when }} ago</span></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="hh">
          <h3>News & press</h3>
          <span class="meta">{{ news.length }} items</span>
        </div>
        <div v-for="n in news" :key="n.t" class="nw">
          <div class="nw-t">{{ n.t }}</div>
          <div class="nw-m">{{ n.when }} · {{ n.src }}</div>
        </div>
        <div class="kicker">Tech stack</div>
        <div class="tech">
          <span v-for="t in account.tech" :key="t" class="tag">{{ t }}</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="hh">
        <h3>Buying group · org chart</h3>
        <span class="meta">5 contacts · 3 warm via mutuals</span>
      </div>
      <div class="org">
        <div class="org-row top">
          <button v-for="m in org.filter(x => ['ceo','coo','cmo'].includes(x.id))" :key="m.id"
            class="node" :class="{ on: selected === m.id }" @click="selected = m.id" type="button">
            <span class="node-avatar" :style="{ background: persColor(m.persona) }">{{ m.name[0] }}</span>
            <div class="node-body">
              <div class="node-name">{{ m.name }}</div>
              <div class="node-role">{{ m.role }}</div>
              <div class="node-tags">
                <span class="pt" :style="{ background: persColor(m.persona) + '33', color: persColor(m.persona) }">{{ m.persona }}</span>
                <span class="it" :class="m.intent">{{ m.intent }}</span>
                <span v-if="m.warm" class="warm">warm ×{{ m.warm }}</span>
              </div>
            </div>
          </button>
        </div>
        <div class="org-row bot">
          <button v-for="m in org.filter(x => ['head','legal'].includes(x.id))" :key="m.id"
            class="node" :class="{ on: selected === m.id }" @click="selected = m.id" type="button">
            <span class="node-avatar" :style="{ background: persColor(m.persona) }">{{ m.name[0] }}</span>
            <div class="node-body">
              <div class="node-name">{{ m.name }}</div>
              <div class="node-role">{{ m.role }}</div>
              <div class="node-tags">
                <span class="pt" :style="{ background: persColor(m.persona) + '33', color: persColor(m.persona) }">{{ m.persona }}</span>
                <span class="it" :class="m.intent">{{ m.intent }}</span>
                <span v-if="m.warm" class="warm">warm ×{{ m.warm }}</span>
              </div>
            </div>
          </button>
        </div>
      </div>

      <div class="leg-row">
        <span><span class="dot" style="background:#34d399"></span>Champion</span>
        <span><span class="dot" style="background:#7c5cff"></span>Decision</span>
        <span><span class="dot" style="background:#22d3ee"></span>Economic</span>
        <span><span class="dot" style="background:#fcd34d"></span>User</span>
        <span><span class="dot" style="background:#f87171"></span>Blocker</span>
      </div>
    </div>

    <div class="card">
      <h3>Mutual connections</h3>
      <p class="meta">Use a warm intro before reaching out cold.</p>
      <div class="muts">
        <div v-for="m in mutuals" :key="m.name" class="mut">
          <div class="m-avatar">{{ m.name.split(' ').map(s => s[0]).join('') }}</div>
          <div>
            <div class="m-name">{{ m.name }} <span class="m-str" :class="m.strength">{{ m.strength }}</span></div>
            <div class="m-via">via {{ m.via }} · {{ m.context }}</div>
          </div>
          <button class="btn btn-ghost sm" type="button">Ask for intro</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ai { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.ah-left { display: flex; gap: 16px; align-items: center; }
.logo { width: 56px; height: 56px; border-radius: 14px; background: linear-gradient(135deg, var(--primary), var(--primary-2)); display: grid; place-items: center; color: #fff; font-weight: 800; font-size: 24px; }
.dm { font-size: 12px; color: var(--text-dim); margin-top: 4px; }
.ah-right { display: flex; align-items: center; gap: 16px; }
.icp { text-align: right; }
.icp-num { font-size: 36px; font-weight: 800; line-height: 1; }
.icp-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 2px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.hh { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; }
.meta { color: var(--text-dim); font-size: 12px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-top: 14px; margin-bottom: 8px; font-weight: 700; }

.signals { display: flex; flex-direction: column; gap: 10px; }
.sg { padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.sg-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 4px; }
.sg-text { font-size: 13px; line-height: 1.4; }
.sg-weight { font-size: 11px; font-weight: 800; padding: 2px 8px; border-radius: 6px; flex-shrink: 0; }
.sg-weight.high { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.sg-weight.med  { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.sg-weight.low  { background: rgba(96, 165, 250, .15); color: #93c5fd; }
.sg-foot { display: flex; gap: 6px; font-size: 11px; color: var(--text-dim); }

.nw { padding: 10px 0; border-bottom: 1px dashed var(--border); }
.nw:last-of-type { border-bottom: 0; }
.nw-t { font-size: 13px; }
.nw-m { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
.tech { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { padding: 4px 10px; border-radius: 6px; background: var(--surface-2); font-size: 11px; border: 1px solid var(--border); }

.org { display: flex; flex-direction: column; gap: 24px; padding: 14px 0; position: relative; }
.org-row { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; position: relative; }
.org-row.top::after { content: ''; position: absolute; left: 50%; bottom: -16px; width: 1px; height: 12px; background: var(--border); }
.node { display: flex; gap: 12px; align-items: center; padding: 12px; min-width: 220px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); cursor: pointer; text-align: left; transition: border-color .15s; }
.node:hover { border-color: var(--primary); }
.node.on { border-color: var(--primary); background: rgba(124, 92, 255, .1); }
.node-avatar { width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; color: #0a0a0f; font-weight: 800; font-size: 14px; flex-shrink: 0; }
.node-name { font-weight: 600; font-size: 13px; }
.node-role { font-size: 11px; color: var(--text-dim); margin: 2px 0 6px; }
.node-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.pt { font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.it { font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.it.high { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.it.med  { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.it.low  { background: var(--surface-2); color: var(--text-dim); }
.warm { font-size: 9px; padding: 2px 6px; border-radius: 4px; background: rgba(34, 211, 238, .15); color: #67e8f9; font-weight: 700; }

.leg-row { display: flex; gap: 14px; flex-wrap: wrap; font-size: 11px; color: var(--text-dim); margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border); }
.leg-row .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }

.muts { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
.mut { display: grid; grid-template-columns: 40px 1fr auto; gap: 12px; align-items: center; padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.m-avatar { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, var(--primary), var(--primary-2)); display: grid; place-items: center; font-weight: 700; font-size: 12px; color: #fff; }
.m-name { font-weight: 600; font-size: 13px; }
.m-str { font-size: 10px; padding: 2px 6px; border-radius: 4px; margin-left: 6px; }
.m-str.strong { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.m-str.medium { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.m-via { font-size: 11px; color: var(--text-dim); }

@media (max-width: 900px) {
  .row { grid-template-columns: 1fr; }
  .node { min-width: 0; flex: 1 1 calc(50% - 7px); }
}
</style>
