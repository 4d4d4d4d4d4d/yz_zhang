<script setup>
import { ref, computed } from 'vue'

const steps = ref([
  { kind: 'email',    day: 0,  subj: 'Lumen × AdForge — quick idea for the Tokyo launch', open: 62, reply: 18, ai: true },
  { kind: 'wait',     day: 2,  duration: '2 days' },
  { kind: 'linkedin', day: 2,  subj: 'Saw your op-ed on localization-first ads — would love to compare notes', open: 81, reply: 24, ai: true },
  { kind: 'wait',     day: 5,  duration: '3 days' },
  { kind: 'email',    day: 5,  subj: 'Re: Tokyo launch — 2-min loom showing how 1 photo → 24 locale variants', open: 48, reply: 14, ai: true },
  { kind: 'wait',     day: 9,  duration: '4 days' },
  { kind: 'call',     day: 9,  subj: 'Try a live call · ~2 min voicemail prepared', open: 35, reply: 8, ai: false }
])
const active = ref(0)

const totalReply = computed(() => {
  let remaining = 100
  let total = 0
  for (const s of steps.value) {
    if (s.kind === 'wait') continue
    const replied = (remaining * s.reply) / 100
    total += replied
    remaining -= replied
  }
  return total
})

const previews = {
  0: {
    title: 'Email · day 0',
    to: 'mei@lumen-studios.jp',
    body: `Hi Mei,\n\nCongrats on the Series A — the Rakuten Beauty partnership looks like a sharp move into JP retail.\n\nWe just helped a comparable Tokyo DTC brand turn one product photo into 24 locale-specific ad variants (JP/KR/SEA) in <72h. Wondering if you'd be open to a short walkthrough?\n\nNo deck. Just the live render and 3 paths to ROAS.\n\n— Akiko`,
    notes: 'AI personalized using Lumen news + Mei\'s public LinkedIn focus.'
  },
  2: {
    title: 'LinkedIn message · day 2',
    to: 'Mei Tanaka',
    body: `Mei — loved your XTECH op-ed on localization-first ads. We're seeing the same insight reflected in early traction. Quick question: do you currently work with one agency per market, or one stack across?`,
    notes: 'Short. Asks a single high-signal question to invite reply.'
  },
  4: {
    title: 'Email · day 5',
    to: 'mei@lumen-studios.jp',
    body: `Mei — re-up on this. Quick 90-sec loom: https://adforge.ai/loom/lumen-jp-render\n\nIt shows your hero shot turning into 9:16 / 1:1 / 16:9 across JP/KR/SEA — captions, voiceover, and platform sizing automatic.\n\nIf the loom is interesting, happy to share the Pareto frontier we mapped for beauty DTC in JP.\n\n— Akiko`,
    notes: 'Concrete proof artifact. Forward-able to her team.'
  },
  6: {
    title: 'Call · day 9',
    to: 'Mei Tanaka',
    body: `Voicemail script (≤45s):\n\n"Hi Mei, Akiko from AdForge. I left two notes about the Tokyo launch — wanted to make sure they didn\'t get lost. We can render 24 locale variants from one shoot in 72h. If that\'s useful, my calendar is open Thursday afternoon JST. Thanks."`,
    notes: 'Last-ditch human touch. Short, dated, specific value.'
  }
}
const preview = computed(() => previews[active.value])
</script>

<template>
  <div class="seq">
    <div class="card head">
      <div>
        <div class="kicker">Cadence · Lumen Studios</div>
        <h3>Multi-channel outreach sequence</h3>
        <p class="meta">7 steps over 9 days · projected total reply rate <strong class="grad-text">{{ totalReply.toFixed(1) }}%</strong></p>
      </div>
      <div class="actions">
        <button class="btn btn-ghost sm" type="button">Duplicate</button>
        <button class="btn btn-primary sm" type="button">Enroll 142 prospects →</button>
      </div>
    </div>

    <div class="grid">
      <div class="card timeline">
        <div v-for="(s, i) in steps" :key="i"
          class="step"
          :class="[s.kind, { on: active === i }]"
          @click="s.kind !== 'wait' && (active = i)">
          <div class="dot" :class="s.kind"></div>
          <div class="step-body">
            <template v-if="s.kind === 'wait'">
              <div class="wait-row">⏳ Wait {{ s.duration }}</div>
            </template>
            <template v-else>
              <div class="s-head">
                <span class="s-day">Day {{ s.day }}</span>
                <span class="s-kind" :class="s.kind">{{ s.kind }}</span>
                <span v-if="s.ai" class="ai-tag">AI</span>
                <span class="s-stats">{{ s.open }}% open · <strong>{{ s.reply }}% reply</strong></span>
              </div>
              <div class="s-subj">{{ s.subj }}</div>
              <div class="rates">
                <div class="rt">
                  <span class="rt-lbl">open</span>
                  <div class="rt-bar"><div class="rt-fill open" :style="{ width: s.open + '%' }"></div></div>
                </div>
                <div class="rt">
                  <span class="rt-lbl">reply</span>
                  <div class="rt-bar"><div class="rt-fill reply" :style="{ width: (s.reply * 4) + '%' }"></div></div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>

      <div class="card preview">
        <div class="ph">
          <h3>{{ preview.title }}</h3>
          <span class="meta">to {{ preview.to }}</span>
        </div>
        <pre>{{ preview.body }}</pre>
        <div class="ai-note">
          <span class="ai-tag">AI</span>
          <span>{{ preview.notes }}</span>
        </div>
        <div class="preview-actions">
          <button class="btn btn-primary sm" type="button">Approve & schedule</button>
          <button class="btn btn-ghost sm" type="button">Regenerate</button>
          <button class="btn btn-ghost sm" type="button">Edit manually</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.seq { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.actions { display: flex; gap: 8px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.grid { display: grid; grid-template-columns: 1.1fr 1fr; gap: 16px; align-items: flex-start; }

.timeline { padding: 18px; position: relative; }
.timeline::before { content: ''; position: absolute; left: 30px; top: 28px; bottom: 28px; width: 1px; background: var(--border); }
.step { display: grid; grid-template-columns: 24px 1fr; gap: 14px; align-items: flex-start; padding: 10px 0; position: relative; }
.step.email, .step.linkedin, .step.call { cursor: pointer; }
.step.on .step-body { background: rgba(124, 92, 255, .08); border-color: var(--primary); }
.dot { width: 24px; height: 24px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; font-size: 11px; position: relative; z-index: 1; }
.dot.email { background: var(--primary); color: #fff; }
.dot.email::before { content: '✉'; }
.dot.linkedin { background: #0a66c2; color: #fff; }
.dot.linkedin::before { content: 'in'; font-weight: 800; font-size: 9px; }
.dot.call { background: var(--accent); color: #fff; }
.dot.call::before { content: '☎'; }
.dot.wait { background: var(--surface); color: var(--text-dim); border: 1px solid var(--border); }
.dot.wait::before { content: '◷'; }
.step-body { padding: 10px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); transition: background .15s, border-color .15s; }
.wait-row { color: var(--text-dim); font-size: 12px; }
.s-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.s-day { font-size: 10px; padding: 2px 8px; border-radius: 4px; background: var(--surface-2); color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; font-weight: 700; }
.s-kind { font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.s-kind.email { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.s-kind.linkedin { background: rgba(10, 102, 194, .2); color: #93c5fd; }
.s-kind.call { background: rgba(255, 122, 217, .15); color: #f5d0fe; }
.ai-tag { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 800; letter-spacing: .05em; }
.s-stats { font-size: 11px; color: var(--text-dim); margin-left: auto; }
.s-stats strong { color: var(--text); }
.s-subj { font-size: 13px; margin-bottom: 8px; }
.rates { display: flex; flex-direction: column; gap: 4px; }
.rt { display: grid; grid-template-columns: 40px 1fr; gap: 8px; align-items: center; }
.rt-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; }
.rt-bar { height: 4px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.rt-fill.open { background: var(--primary-2); }
.rt-fill.reply { background: var(--success); }

.preview { padding: 20px; position: sticky; top: 90px; }
.ph { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; }
.preview pre { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; color: var(--text); font-family: inherit; font-size: 13px; line-height: 1.65; margin: 0 0 12px; white-space: pre-wrap; }
.ai-note { display: flex; gap: 8px; align-items: flex-start; padding: 10px 12px; background: rgba(124, 92, 255, .08); border: 1px solid rgba(124, 92, 255, .25); border-radius: 8px; font-size: 12px; color: var(--text-dim); margin-bottom: 14px; }
.preview-actions { display: flex; gap: 8px; flex-wrap: wrap; }

@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; }
  .preview { position: static; }
}
</style>
