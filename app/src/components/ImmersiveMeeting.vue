<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { routeCaption } from '../logic/interpreter.js'
import { overlapWindows } from '../logic/meeting.js'

const PARTICIPANTS = [
  { id: 'yu',    name: 'Yu Chen',      role: 'Seller · Shanghai', lang: 'zh', tz: 8,  hue: 262 },
  { id: 'anna',  name: 'Anna Weber',   role: 'Buyer · Berlin',    lang: 'de', tz: 2,  hue: 190 },
  { id: 'диего', name: 'Diego Reyes',  role: 'Buyer · CDMX',      lang: 'es', tz: -6, hue: 320 },
  { id: 'sam',   name: 'Sam Ortiz',    role: 'AdForge · SF',      lang: 'en', tz: -7, hue: 152 }
]

const GLOSSARY = [
  { term: 'AdForge', keep: true },
  { term: 'trust link', translations: { zh: '信任链接', de: 'Trust-Link', es: 'enlace de confianza', en: 'trust link' } },
  { term: 'MOQ', keep: true }
]

const SCRIPTED = [
  { speakerId: 'yu',   lang: 'zh', text: '我们的产线月产能是 12 万件，MOQ 是 5000。' ,
    gloss: { de: 'Unsere Linie schafft 120k Stück/Monat, MOQ ist 5000.', es: 'Nuestra línea produce 120k unidades/mes, MOQ es 5000.', en: 'Our line does 120k units/month, MOQ is 5000.' } },
  { speakerId: 'anna', lang: 'de', text: 'Können wir die Qualitätsberichte über einen trust link teilen?',
    gloss: { zh: '我们能通过信任链接共享质检报告吗？', es: '¿Podemos compartir los informes de calidad por enlace de confianza?', en: 'Can we share the QA reports via trust link?' } },
  { speakerId: 'sam',  lang: 'en', text: 'Yes — AdForge issues a scoped trust link with the verified metrics.',
    gloss: { zh: '可以——AdForge 会签发带核验指标的限权信任链接。', de: 'Ja — AdForge stellt einen Trust-Link mit verifizierten Kennzahlen aus.', es: 'Sí — AdForge emite un enlace de confianza con métricas verificadas.' } },
  { speakerId: 'диего', lang: 'es', text: 'Perfecto. ¿El MOQ baja si firmamos anual?',
    gloss: { zh: '很好。签年度合同的话 MOQ 能降吗？', de: 'Perfekt. Sinkt das MOQ bei einem Jahresvertrag?', en: 'Great. Does the MOQ drop on an annual contract?' } }
]

const viewer = ref('anna')
const feed = ref([])
const speaking = ref(null)
let idx = 0
let timer

function tick() {
  const line = SCRIPTED[idx % SCRIPTED.length]
  idx++
  speaking.value = line.speakerId
  const session = { participants: PARTICIPANTS }
  // Route with pre-translated bodies (demo stands in for the MT engine),
  // then let the glossary layer enforce protected terms on each caption.
  const captions = routeCaption(line, session, GLOSSARY).map(c => {
    const body = c.verbatim ? c.text : (line.gloss[c.lang] || c.text)
    const enforced = routeCaption({ ...line, text: body }, { participants: [{ id: c.to, lang: c.lang }] }, GLOSSARY)
    return { ...c, text: enforced[0]?.text ?? body, protected: enforced[0]?.protected ?? [] }
  })
  feed.value.unshift({ id: idx, speaker: PARTICIPANTS.find(p => p.id === line.speakerId), original: line.text, captions })
  if (feed.value.length > 6) feed.value.pop()
}

onMounted(() => { tick(); timer = setInterval(tick, 3200) })
onBeforeUnmount(() => clearInterval(timer))

const myCaption = entry => entry.captions.find(c => c.to === viewer.value)

const schedule = computed(() => overlapWindows(PARTICIPANTS, { startLocal: 8, endLocal: 20 }))
const fmtH = h => `${String(Math.floor(h)).padStart(2, '0')}:${h % 1 ? '30' : '00'}`
</script>

<template>
  <div class="imm">
    <div class="card head">
      <div>
        <div class="kicker">Immersive meeting · live interpreter</div>
        <h3>Everyone speaks their own language — everyone understands</h3>
        <p class="meta">Live captions per attendee with glossary-protected terms (product names never get mistranslated). Scheduler finds humane windows across {{ PARTICIPANTS.length }} time zones.</p>
      </div>
      <label class="as">Viewing as
        <select v-model="viewer">
          <option v-for="p in PARTICIPANTS" :key="p.id" :value="p.id">{{ p.name }} ({{ p.lang }})</option>
        </select>
      </label>
    </div>

    <div class="room card">
      <div class="seats">
        <div v-for="p in PARTICIPANTS" :key="p.id" class="seat" :class="{ talking: speaking === p.id }" :style="{ '--h': p.hue }">
          <div class="ava">{{ p.name[0] }}</div>
          <div class="sn">{{ p.name }}</div>
          <div class="sr">{{ p.role }}</div>
          <div class="ring"></div>
        </div>
      </div>

      <div class="feed">
        <div v-for="e in feed" :key="e.id" class="line">
          <div class="orig"><b>{{ e.speaker.name }}</b> <span class="ol">({{ e.speaker.lang }})</span> {{ e.original }}</div>
          <div v-if="myCaption(e)" class="cap">
            <span class="cl">{{ myCaption(e).verbatim ? 'verbatim' : myCaption(e).latencyMs + 'ms' }}</span>
            {{ myCaption(e).text }}
            <span v-for="pr in myCaption(e).protected" :key="pr.term" class="prot">🔒 {{ pr.rendered }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="card sched">
      <h3>Cross-timezone scheduler</h3>
      <template v-if="schedule.windows.length">
        <p class="meta">{{ schedule.windows.length }} window(s) where all {{ PARTICIPANTS.length }} attendees are inside 08:00–20:00 local:</p>
        <div v-for="(w, i) in schedule.windows" :key="i" class="win">
          <b>{{ fmtH(w.startUtc) }}–{{ fmtH(w.endUtc) }} UTC</b>
          <span class="score">comfort {{ (w.score * 100).toFixed(0) }}%</span>
          <span v-for="p in PARTICIPANTS" :key="p.id" class="lt">{{ p.name.split(' ')[0] }} {{ fmtH((w.startUtc + p.tz + 24) % 24) }}</span>
        </div>
      </template>
      <template v-else-if="schedule.bestCompromise">
        <p class="meta warn">No window fits everyone. Best compromise: {{ fmtH(schedule.bestCompromise.startUtc) }} UTC — {{ schedule.bestCompromise.attendeesIn }}/{{ schedule.bestCompromise.of }} attendees in hours.</p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.imm { display: flex; flex-direction: column; gap: 16px; }
.card { padding: 18px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; flex-wrap: wrap; }
.head h3 { margin: 4px 0 6px; }
.meta { color: var(--text-dim); font-size: 13px; margin: 0; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.as { display: flex; flex-direction: column; gap: 6px; font-size: 11px; color: var(--text-dim); }
select { padding: 7px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 12px; }

.seats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.seat { position: relative; display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 16px 8px 12px; border-radius: 14px; border: 1px solid var(--border); background: radial-gradient(ellipse at top, hsl(var(--h) 60% 18% / .6), transparent 70%); }
.ava { width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; background: hsl(var(--h) 65% 45%); color: #fff; font-weight: 800; font-size: 17px; }
.sn { font-size: 12px; font-weight: 700; margin-top: 4px; }
.sr { font-size: 10px; color: var(--text-dim); }
.ring { position: absolute; inset: 0; border-radius: 14px; border: 2px solid transparent; pointer-events: none; }
.seat.talking .ring { border-color: hsl(var(--h) 70% 55%); animation: talk 1s ease-in-out infinite alternate; }
@keyframes talk { from { opacity: .4; } to { opacity: 1; } }

.feed { display: flex; flex-direction: column; gap: 10px; }
.line { border: 1px solid var(--border); border-radius: 12px; padding: 10px 12px; }
.orig { font-size: 12px; color: var(--text-dim); }
.orig b { color: var(--text); }
.ol { font-size: 10px; }
.cap { margin-top: 6px; font-size: 13px; }
.cl { font-size: 9px; padding: 2px 7px; border-radius: 999px; background: var(--surface-2); color: var(--text-dim); margin-right: 6px; }
.prot { font-size: 10px; margin-left: 8px; color: #34d399; }

.sched h3 { margin: 0 0 8px; font-size: 15px; }
.win { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; padding: 9px 12px; border: 1px solid var(--border); border-radius: 10px; margin-top: 8px; font-size: 12px; }
.score { font-size: 10px; color: #22d3ee; }
.lt { font-size: 11px; color: var(--text-dim); }
.warn { color: #fbbf24; }

@media (max-width: 800px) { .seats { grid-template-columns: repeat(2, 1fr); } }
</style>
