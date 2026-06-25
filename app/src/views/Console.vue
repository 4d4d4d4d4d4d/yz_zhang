<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import SecurityRibbon from '../components/SecurityRibbon.vue'
import SubTabs from '../components/SubTabs.vue'

import RecommendDeep     from '../components/RecommendDeep.vue'
import RecommendAdvanced from '../components/RecommendAdvanced.vue'

import MarketingHub     from '../components/MarketingHub.vue'
import MarketingControl from '../components/MarketingControl.vue'

import BusinessMatchHub from '../components/BusinessMatchHub.vue'
import PipelineBoard    from '../components/PipelineBoard.vue'

import DealRoom              from '../components/DealRoom.vue'
import NegotiationPlaybook   from '../components/NegotiationPlaybook.vue'

import TrustCenter      from '../components/TrustCenter.vue'
import ControlsRegister from '../components/ControlsRegister.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const sections = [
  {
    key: 'recommend', icon: '🧠',
    sub: [
      { v: 'inputs',   label: 'Inputs & ranking', comp: RecommendDeep },
      { v: 'agents',   label: 'Multi-agent pipeline', comp: RecommendAdvanced }
    ]
  },
  {
    key: 'marketing', icon: '📈',
    sub: [
      { v: 'overview', label: 'Overview', comp: MarketingHub },
      { v: 'control',  label: 'Campaigns + A/B + Geo', comp: MarketingControl }
    ]
  },
  {
    key: 'partners', icon: '🤝',
    sub: [
      { v: 'network',  label: 'Network profile', comp: BusinessMatchHub },
      { v: 'pipeline', label: 'Pipeline board', comp: PipelineBoard }
    ]
  },
  {
    key: 'deals', icon: '📝',
    sub: [
      { v: 'room',     label: 'Deal room', comp: DealRoom },
      { v: 'playbook', label: 'Playbook · ZOPA · redline', comp: NegotiationPlaybook }
    ]
  },
  {
    key: 'trust', icon: '🛡',
    sub: [
      { v: 'posture',  label: 'Posture', comp: TrustCenter },
      { v: 'controls', label: 'Controls · DSR · runbook', comp: ControlsRegister }
    ]
  }
]

const active = computed(() => sections.find(s => s.key === route.params.tab) || sections[0])

const subTab = ref(active.value.sub[0].v)
watch(() => active.value.key, () => { subTab.value = active.value.sub[0].v })

const subTabs = computed(() => active.value.sub.map(s => ({ v: s.v, label: s.label })))
const activeComp = computed(() => active.value.sub.find(s => s.v === subTab.value)?.comp)
</script>

<template>
  <section class="console section--tight">
    <div class="container shell">
      <aside class="side card">
        <div class="ws">
          <div class="ws-logo">A</div>
          <div>
            <div class="ws-name">AdForge Workspace</div>
            <div class="ws-org">Lumi DTC · Enterprise</div>
          </div>
        </div>
        <div class="kicker">Modules</div>
        <nav class="nav">
          <router-link v-for="s in sections" :key="s.key"
            :to="{ name: 'console', params: { tab: s.key } }"
            class="nav-item" :class="{ on: active.key === s.key }">
            <span class="ico">{{ s.icon }}</span>
            <span>{{ t(`console.s.${s.key}.title`) }}</span>
          </router-link>
        </nav>
        <div class="hint card">
          <div class="kicker">Need help?</div>
          <p>Talk to a partner manager — typically replies within 1 business day.</p>
          <router-link to="/contact" class="btn btn-ghost sm">{{ t('cta.contact') }}</router-link>
        </div>
      </aside>

      <main class="main">
        <SecurityRibbon />

        <div class="m-head">
          <h2 class="grad-text">{{ t(`console.s.${active.key}.title`) }}</h2>
          <p>{{ t(`console.s.${active.key}.sub`) }}</p>
        </div>

        <SubTabs v-model="subTab" :tabs="subTabs" />

        <component :is="activeComp" :key="active.key + '/' + subTab" />
      </main>
    </div>
  </section>
</template>

<style scoped>
.console { padding-top: 40px; }
.shell { display: grid; grid-template-columns: 260px 1fr; gap: 24px; align-items: flex-start; }
.side { padding: 18px; position: sticky; top: 90px; display: flex; flex-direction: column; gap: 14px; }
.ws { display: flex; align-items: center; gap: 10px; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
.ws-logo { width: 36px; height: 36px; border-radius: 10px; background: linear-gradient(135deg, var(--primary), var(--primary-2)); display: grid; place-items: center; color: #fff; font-weight: 800; }
.ws-name { font-weight: 700; font-size: 13px; }
.ws-org { font-size: 11px; color: var(--text-dim); }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 6px; }
.nav { display: flex; flex-direction: column; gap: 4px; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; color: var(--text-dim); font-size: 14px; }
.nav-item:hover { background: var(--surface); color: var(--text); }
.nav-item.on { background: rgba(124, 92, 255, .15); color: #fff; border: 1px solid rgba(124, 92, 255, .35); padding: 9px 11px; }
.ico { font-size: 16px; }
.hint { margin-top: auto; padding: 14px; background: rgba(124, 92, 255, .06); border-color: rgba(124, 92, 255, .25); }
.hint p { margin: 4px 0 12px; font-size: 12px; color: var(--text-dim); }
.btn.sm { padding: 6px 12px; font-size: 12px; justify-content: center; width: 100%; }

.main { min-width: 0; }
.m-head { margin-bottom: 20px; }
.m-head h2 { font-size: 32px; }
.m-head p { margin: 6px 0 0; color: var(--text-dim); }

@media (max-width: 900px) {
  .shell { grid-template-columns: 1fr; }
  .side { position: static; }
  .nav { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
  .hint { display: none; }
}
</style>
