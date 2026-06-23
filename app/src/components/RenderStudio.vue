<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const assets = [
  { id: 'sneaker', label: 'Sneaker · still', c1: '#7c5cff', c2: '#22d3ee' },
  { id: 'serum',   label: 'Skincare · still', c1: '#ff7ad9', c2: '#fbbf24' },
  { id: 'gadget',  label: 'Tech · 5s clip',  c1: '#22d3ee', c2: '#34d399' },
  { id: 'apparel', label: 'Apparel · still',  c1: '#60a5fa', c2: '#7c5cff' }
]
const formats = [
  { id: '9x16', label: '9:16 · short video' },
  { id: '1x1',  label: '1:1 · feed' },
  { id: '16x9', label: '16:9 · landscape' },
  { id: '6s',   label: '6s · bumper' }
]
const markets = [
  { id: 'US', label: 'United States', lang: 'en-US' },
  { id: 'JP', label: 'Japan', lang: 'ja-JP' },
  { id: 'KR', label: 'Korea', lang: 'ko-KR' },
  { id: 'BR', label: 'Brazil', lang: 'pt-BR' },
  { id: 'DE', label: 'Germany', lang: 'de-DE' },
  { id: 'MX', label: 'Mexico', lang: 'es-MX' },
  { id: 'SEA', label: 'SEA (TH/ID/VN)', lang: 'multi' },
  { id: 'FR', label: 'France', lang: 'fr-FR' }
]

const asset = ref('sneaker')
const fmt = ref(['9x16', '1x1'])
const targets = ref(['US', 'JP', 'BR'])
const status = ref('idle') // idle | rendering | done
const queue = ref([])

const currentAsset = computed(() => assets.find(a => a.id === asset.value))
const planned = computed(() => fmt.value.length * targets.value.length)

function toggle(list, id) {
  const i = list.indexOf(id)
  if (i >= 0) list.splice(i, 1); else list.push(id)
}

async function render() {
  if (!fmt.value.length || !targets.value.length) return
  status.value = 'rendering'
  queue.value = []
  for (const m of targets.value) {
    for (const f of fmt.value) {
      const mk = markets.find(x => x.id === m)
      queue.value.push({
        id: `${m}-${f}`,
        market: mk.label,
        lang: mk.lang,
        format: formats.find(x => x.id === f).label,
        progress: 0
      })
    }
  }
  for (const item of queue.value) {
    await new Promise(res => setTimeout(res, 240))
    while (item.progress < 100) {
      await new Promise(res => setTimeout(res, 60))
      item.progress = Math.min(100, item.progress + 8 + Math.random() * 14)
    }
  }
  status.value = 'done'
}
</script>

<template>
  <div class="studio card">
    <div class="left">
      <div class="kicker">{{ t('studio.pickAsset') }}</div>
      <div class="assets">
        <button v-for="a in assets" :key="a.id"
          class="asset" :class="{ on: asset === a.id }"
          @click="asset = a.id" type="button">
          <div class="thumb" :style="{ background: `linear-gradient(135deg, ${a.c1}, ${a.c2})` }"></div>
          <span>{{ a.label }}</span>
        </button>
      </div>

      <div class="kicker">{{ t('studio.pickFormat') }}</div>
      <div class="chips">
        <button v-for="f in formats" :key="f.id"
          class="chip" :class="{ on: fmt.includes(f.id) }"
          @click="toggle(fmt, f.id)" type="button">{{ f.label }}</button>
      </div>

      <div class="kicker">{{ t('studio.pickMarkets') }}</div>
      <div class="chips">
        <button v-for="m in markets" :key="m.id"
          class="chip" :class="{ on: targets.includes(m.id) }"
          @click="toggle(targets, m.id)" type="button">{{ m.label }}</button>
      </div>

      <button class="btn btn-primary go" :disabled="status === 'rendering'" @click="render" type="button">
        <span v-if="status === 'rendering'">{{ t('studio.rendering') }}</span>
        <span v-else>{{ t('studio.renderBtn') }} →</span>
      </button>
      <p class="notes">{{ t('studio.notes') }}</p>
    </div>

    <div class="right">
      <div class="preview" :style="{ background: `linear-gradient(135deg, ${currentAsset.c1}, ${currentAsset.c2})` }">
        <div class="film-grain"></div>
        <div class="badge" v-if="status === 'rendering'">● Rendering</div>
        <div class="badge done" v-else-if="status === 'done'">✓ {{ t('studio.done') }}</div>
        <div class="badge idle" v-else>● Idle</div>
      </div>

      <div class="queue">
        <div class="queue-head">
          <h3>{{ t('studio.queueTitle') }}</h3>
          <span class="meta">{{ planned }} {{ t('studio.outputs') }}</span>
        </div>
        <div class="qlist" v-if="queue.length">
          <div v-for="q in queue" :key="q.id" class="qitem">
            <div class="qmeta">
              <strong>{{ q.market }}</strong>
              <span class="qfmt">{{ q.format }} · {{ q.lang }}</span>
            </div>
            <div class="qbar"><div class="qfill" :style="{ width: q.progress + '%' }"></div></div>
            <div class="qpct">{{ Math.round(q.progress) }}%</div>
          </div>
        </div>
        <div v-else class="empty">No renders yet — pick an asset and markets, then render.</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.studio { display: grid; grid-template-columns: 1fr 1.2fr; gap: 28px; padding: 28px; }
.kicker { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin: 18px 0 10px; }
.kicker:first-child { margin-top: 0; }

.assets { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.asset { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 10px; display: flex; align-items: center; gap: 10px; cursor: pointer; color: var(--text); font-size: 13px; text-align: left; }
.asset.on { border-color: var(--primary); background: rgba(124, 92, 255, .12); }
.thumb { width: 38px; height: 38px; border-radius: 8px; flex-shrink: 0; }

.chips { display: flex; gap: 8px; flex-wrap: wrap; }
.chip { padding: 8px 12px; border-radius: 999px; background: var(--surface); color: var(--text); border: 1px solid var(--border); cursor: pointer; font-size: 13px; }
.chip.on { background: rgba(124, 92, 255, .2); border-color: var(--primary); color: #fff; }

.go { margin-top: 20px; width: 100%; justify-content: center; }
.go:disabled { opacity: .7; cursor: not-allowed; }
.notes { font-size: 12px; color: var(--text-dim); margin-top: 12px; }

.preview {
  aspect-ratio: 16 / 9; border-radius: 14px; border: 1px solid var(--border);
  position: relative; overflow: hidden;
}
.film-grain {
  position: absolute; inset: 0;
  background-image: radial-gradient(rgba(255,255,255,.08) 1px, transparent 1px);
  background-size: 4px 4px; mix-blend-mode: overlay; opacity: .4;
  animation: shift 8s linear infinite;
}
@keyframes shift { from { background-position: 0 0; } to { background-position: 80px 80px; } }
.badge {
  position: absolute; left: 14px; top: 14px;
  padding: 6px 10px; border-radius: 999px; font-size: 12px;
  background: rgba(0,0,0,.5); color: #fff; border: 1px solid rgba(255,255,255,.15);
}
.badge.done { background: rgba(52, 211, 153, .2); color: #6ee7b7; border-color: rgba(52, 211, 153, .4); }
.badge.idle { background: rgba(255,255,255,.08); }

.queue { margin-top: 20px; }
.queue-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; }
.meta { font-size: 13px; color: var(--text-dim); }
.qlist { display: flex; flex-direction: column; gap: 10px; max-height: 260px; overflow-y: auto; }
.qitem { display: grid; grid-template-columns: 1.4fr 1.4fr 60px; gap: 12px; align-items: center; padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
.qmeta { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.qfmt { color: var(--text-dim); font-size: 12px; }
.qbar { height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.qfill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); transition: width .15s ease; }
.qpct { font-size: 12px; color: var(--text-dim); font-variant-numeric: tabular-nums; text-align: right; }
.empty { color: var(--text-dim); padding: 16px; border: 1px dashed var(--border); border-radius: 10px; text-align: center; font-size: 13px; }

@media (max-width: 900px) { .studio { grid-template-columns: 1fr; } }
</style>
