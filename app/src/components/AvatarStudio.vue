<script setup>
import { ref, computed } from 'vue'
import { PERSONAS, PLATFORM_CAPS, planStoryboard, localizeVariants } from '../logic/avatar.js'

const LANG_LABEL = { en: 'English', zh: '中文', ja: '日本語', es: 'Español', de: 'Deutsch' }

const personaId = ref('mira')
const platform = ref('tiktok')
const language = ref('en')
const script = ref(
  'Meet AdForge — your creative team for every market. One product photo becomes a full campaign, localized end to end. ' +
  'Our render farm ships platform-ready cuts in minutes, not weeks. Every video carries content credentials your buyers can verify. ' +
  'Book a live demo today and launch your next market this quarter. We handle voice, format and compliance for you.'
)
const variantLangs = ref(['es', 'ja'])

const persona = computed(() => PERSONAS.find(p => p.id === personaId.value))
const plan = computed(() => planStoryboard(script.value, {
  persona: personaId.value, language: language.value, platform: platform.value
}))
const variants = computed(() => localizeVariants(plan.value, variantLangs.value))

function toggleVariant(l) {
  const i = variantLangs.value.indexOf(l)
  i >= 0 ? variantLangs.value.splice(i, 1) : variantLangs.value.push(l)
}
</script>

<template>
  <div class="avs">
    <div class="card head">
      <div>
        <div class="kicker">Digital human · AI marketing video</div>
        <h3>One script, a native presenter in every market</h3>
        <p class="meta">Pick a persona, paste the approved script — get a timed storyboard with lip-sync hints and per-language variants. Synthetic-media disclosure is always on.</p>
      </div>
    </div>

    <div class="grid">
      <div class="card form">
        <div class="f-sec">
          <div class="kicker">Persona</div>
          <div class="personas">
            <button v-for="p in PERSONAS" :key="p.id" type="button"
              class="persona" :class="{ on: personaId === p.id }" @click="personaId = p.id">
              <span class="face">{{ p.name[0] }}</span>
              <span class="pn">{{ p.name }}</span>
              <span class="ps">{{ p.style }}</span>
              <span class="pl">{{ p.languages.join(' · ') }}</span>
            </button>
          </div>
        </div>

        <div class="f-sec row">
          <label>Platform
            <select v-model="platform">
              <option v-for="(cap, k) in PLATFORM_CAPS" :key="k" :value="k">{{ k }} · ≤{{ cap }}s</option>
            </select>
          </label>
          <label>Master language
            <select v-model="language">
              <option v-for="l in persona.languages" :key="l" :value="l">{{ LANG_LABEL[l] }}</option>
            </select>
          </label>
        </div>

        <div class="f-sec">
          <div class="kicker">Script</div>
          <textarea v-model="script" rows="6" aria-label="Presenter script"></textarea>
        </div>

        <div class="f-sec">
          <div class="kicker">Localized variants</div>
          <button v-for="l in ['en','zh','ja','es','de']" :key="l" type="button"
            class="chip" :class="{ on: variantLangs.includes(l) }" @click="toggleVariant(l)">
            {{ LANG_LABEL[l] }}
          </button>
        </div>
      </div>

      <div class="card board">
        <div class="b-head">
          <h3>Storyboard · {{ plan.scenes.length }} scenes · {{ plan.totalSeconds }}s / {{ plan.cap }}s</h3>
          <span class="disc">⚠ {{ plan.disclosure }} label</span>
        </div>
        <p v-if="plan.truncated" class="trunc">Platform cap reached — {{ plan.dropped.length }} scene(s) cut at the boundary: “{{ plan.dropped[0].text.slice(0, 48) }}…”</p>

        <ol class="scenes">
          <li v-for="sc in plan.scenes" :key="sc.idx">
            <span class="t">{{ sc.seconds }}s</span>
            <span class="g">{{ sc.gesture }}</span>
            <span class="tx">{{ sc.text }}</span>
            <span class="ls">{{ sc.lipSync }} sync pts</span>
          </li>
        </ol>

        <div class="vars">
          <div class="kicker">Variants</div>
          <div v-for="v in variants.variants" :key="v.language" class="var">
            <b>{{ LANG_LABEL[v.language] }}</b>
            <span>{{ v.totalSeconds }}s · {{ v.scenes.length }} scenes</span>
            <span class="ok">ready to render</span>
          </div>
          <div v-for="l in variants.skipped" :key="l" class="var skip">
            <b>{{ LANG_LABEL[l] }}</b>
            <span>persona {{ persona.name }} doesn’t speak this — switch persona or skip</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.avs { display: flex; flex-direction: column; gap: 16px; }
.card { padding: 18px; }
.head h3 { margin: 4px 0 6px; }
.meta { color: var(--text-dim); font-size: 13px; margin: 0; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 8px; }
.grid { display: grid; grid-template-columns: 5fr 7fr; gap: 14px; align-items: start; }

.f-sec { margin-bottom: 16px; }
.f-sec.row { display: flex; gap: 14px; }
.f-sec label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--text-dim); flex: 1; }
select, textarea { padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 13px; width: 100%; }
textarea { resize: vertical; line-height: 1.5; }

.personas { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.persona { display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 10px 6px; border-radius: 12px; border: 1px solid var(--border); background: var(--surface); cursor: pointer; color: var(--text-dim); }
.persona.on { border-color: rgba(124, 92, 255, .55); background: rgba(124, 92, 255, .12); color: var(--text); }
.face { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; font-weight: 800; }
.pn { font-size: 12px; font-weight: 700; }
.ps { font-size: 10px; }
.pl { font-size: 9px; opacity: .8; }

.chip { display: inline-block; margin: 0 6px 6px 0; padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text-dim); font-size: 12px; cursor: pointer; }
.chip.on { border-color: rgba(124, 92, 255, .5); background: rgba(124, 92, 255, .15); color: #fff; }

.b-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.b-head h3 { margin: 0; font-size: 15px; }
.disc { font-size: 10px; padding: 3px 9px; border-radius: 999px; background: rgba(251, 191, 36, .14); color: #fbbf24; border: 1px solid rgba(251, 191, 36, .4); }
.trunc { font-size: 12px; color: #fbbf24; margin: 10px 0 0; }

.scenes { list-style: none; margin: 14px 0; padding: 0; display: flex; flex-direction: column; gap: 8px; counter-reset: sc; }
.scenes li { display: grid; grid-template-columns: 44px 76px 1fr auto; gap: 10px; align-items: baseline; padding: 9px 12px; border: 1px solid var(--border); border-radius: 10px; font-size: 12px; }
.t { font-variant-numeric: tabular-nums; font-weight: 700; }
.g { font-size: 10px; color: #22d3ee; text-transform: uppercase; letter-spacing: .05em; }
.tx { color: var(--text-dim); }
.ls { font-size: 10px; color: var(--text-dim); white-space: nowrap; }

.vars { border-top: 1px dashed var(--border); padding-top: 12px; }
.var { display: flex; gap: 12px; align-items: baseline; font-size: 12px; padding: 5px 0; color: var(--text-dim); }
.var b { color: var(--text); min-width: 80px; }
.ok { color: #34d399; font-size: 11px; }
.var.skip { color: #fbbf24; }

@media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } .personas { grid-template-columns: repeat(4, 1fr); } }
</style>
