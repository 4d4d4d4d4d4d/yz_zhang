<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { SECTIONS } from '../console/registry.js'
import { recordSection } from '../store/workspace.js'

import SecurityRibbon  from '../components/SecurityRibbon.vue'
import NotificationCenter from '../components/NotificationCenter.vue'
import ModuleBoundary     from '../components/ModuleBoundary.vue'
import SubTabs         from '../components/SubTabs.vue'
import LiveActivityFeed from '../components/LiveActivityFeed.vue'

import RecommendDeep     from '../components/RecommendDeep.vue'
import RecommendAdvanced from '../components/RecommendAdvanced.vue'
import ModelRegistry     from '../components/ModelRegistry.vue'
import BanditExplorer    from '../components/BanditExplorer.vue'
import FeatureStore      from '../components/FeatureStore.vue'
import ExperimentManager from '../components/ExperimentManager.vue'
import UsageMetering     from '../components/UsageMetering.vue'
import PersonalizationDash from '../components/PersonalizationDash.vue'

import MarketingHub        from '../components/MarketingHub.vue'
import MarketingControl    from '../components/MarketingControl.vue'
import AttributionWaterfall from '../components/AttributionWaterfall.vue'
import AudienceBuilder     from '../components/AudienceBuilder.vue'
import CohortRetention     from '../components/CohortRetention.vue'
import ForecastSim         from '../components/ForecastSim.vue'
import FunnelView          from '../components/FunnelView.vue'
import RevenueDashboard    from '../components/RevenueDashboard.vue'
import UpsellEngine        from '../components/UpsellEngine.vue'

import BusinessMatchHub from '../components/BusinessMatchHub.vue'
import PipelineBoard    from '../components/PipelineBoard.vue'
import AccountIntel     from '../components/AccountIntel.vue'
import OutreachSequence from '../components/OutreachSequence.vue'
import SalesForecast    from '../components/SalesForecast.vue'
import TerritoryQuota   from '../components/TerritoryQuota.vue'
import OrderBook       from '../components/OrderBook.vue'
import MarketplaceCommission from '../components/MarketplaceCommission.vue'

import DealRoom              from '../components/DealRoom.vue'
import NegotiationPlaybook   from '../components/NegotiationPlaybook.vue'
import ApprovalFlow          from '../components/ApprovalFlow.vue'
import ClauseLibrary         from '../components/ClauseLibrary.vue'
import ObligationTracker     from '../components/ObligationTracker.vue'
import ContractAnalytics     from '../components/ContractAnalytics.vue'
import CPQEditor             from '../components/CPQEditor.vue'
import RevenueRecognition    from '../components/RevenueRecognition.vue'

import AvatarStudio      from '../components/AvatarStudio.vue'
import ImmersiveMeeting  from '../components/ImmersiveMeeting.vue'
import VirtualTour       from '../components/VirtualTour.vue'
import FieldVerification from '../components/FieldVerification.vue'

import ShowcaseGallery   from '../components/ShowcaseGallery.vue'
import TrustLinkBuilder  from '../components/TrustLinkBuilder.vue'
import VerificationQueue from '../components/VerificationQueue.vue'
import TrustPipeline     from '../components/TrustPipeline.vue'
import DealReportCard    from '../components/DealReportCard.vue'

import TrustCenter      from '../components/TrustCenter.vue'
import ControlsRegister from '../components/ControlsRegister.vue'
import RiskHeatmap      from '../components/RiskHeatmap.vue'
import DPIAWorkflow     from '../components/DPIAWorkflow.vue'
import AuditRoom        from '../components/AuditRoom.vue'
import PolicyManagement from '../components/PolicyManagement.vue'
import CustomerHealth   from '../components/CustomerHealth.vue'
import SupportSLA       from '../components/SupportSLA.vue'

const { t } = useI18n()
const route = useRoute()

// Component wiring stays in the view (it imports .vue files); the
// structure (keys, order, sub list) comes from the single-source
// registry (spec 20). Keyed by `section/sub`.
const COMPONENTS = {
  'recommend/inputs': RecommendDeep, 'recommend/agents': RecommendAdvanced, 'recommend/registry': ModelRegistry,
  'recommend/bandit': BanditExplorer, 'recommend/features': FeatureStore, 'recommend/experiments': ExperimentManager,
  'recommend/metering': UsageMetering, 'recommend/tenant': PersonalizationDash,
  'marketing/overview': MarketingHub, 'marketing/control': MarketingControl, 'marketing/attribution': AttributionWaterfall,
  'marketing/audience': AudienceBuilder, 'marketing/retention': CohortRetention, 'marketing/forecast': ForecastSim,
  'marketing/revenue': RevenueDashboard, 'marketing/upsell': UpsellEngine, 'marketing/funnel': FunnelView,
  'partners/network': BusinessMatchHub, 'partners/pipeline': PipelineBoard, 'partners/intel': AccountIntel,
  'partners/outreach': OutreachSequence, 'partners/forecast': SalesForecast, 'partners/territory': TerritoryQuota,
  'partners/orders': OrderBook, 'partners/commission': MarketplaceCommission,
  'deals/room': DealRoom, 'deals/playbook': NegotiationPlaybook, 'deals/workflow': ApprovalFlow,
  'deals/library': ClauseLibrary, 'deals/obligations': ObligationTracker, 'deals/analytics': ContractAnalytics,
  'deals/cpq': CPQEditor, 'deals/revrec': RevenueRecognition,
  'showcase/gallery': ShowcaseGallery, 'showcase/links': TrustLinkBuilder, 'showcase/verification': VerificationQueue,
  'showcase/pipeline': TrustPipeline, 'showcase/report': DealReportCard,
  'immersive/avatar': AvatarStudio, 'immersive/meeting': ImmersiveMeeting, 'immersive/tour': VirtualTour,
  'immersive/field': FieldVerification,
  'trust/posture': TrustCenter, 'trust/controls': ControlsRegister, 'trust/heatmap': RiskHeatmap,
  'trust/dpia': DPIAWorkflow, 'trust/audit': AuditRoom, 'trust/policies': PolicyManagement,
  'trust/health': CustomerHealth, 'trust/support': SupportSLA
}

const sections = SECTIONS.map(s => ({
  key: s.key,
  icon: s.icon,
  sub: s.subs.map(v => {
    const comp = COMPONENTS[`${s.key}/${v}`]
    if (!comp) throw new Error(`Console: no component wired for ${s.key}/${v}`)
    return { v, comp }
  })
}))

const active = computed(() => sections.find(s => s.key === route.params.tab) || sections[0])

// ?sub= deep link (spec 24): palette hits and share links can target a sub-tab.
const requestedSub = () => {
  const q = route.query.sub
  return active.value.sub.some(s => s.v === q) ? q : active.value.sub[0].v
}
const subTab = ref(requestedSub())
watch(() => [active.value.key, route.query.sub], () => { subTab.value = requestedSub() })

// Spec 32 — remember visited sections for the ⌘K empty-query jump list.
watch(() => active.value.key, k => recordSection(k), { immediate: true })

const subTabs = computed(() => active.value.sub.map(s => ({ v: s.v, label: t(`console.tabs.${active.value.key}.${s.v}`) })))
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
            <span class="cnt">{{ s.sub.length }}</span>
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
          <div class="m-title">
            <h2 class="grad-text">{{ t(`console.s.${active.key}.title`) }}</h2>
            <NotificationCenter />
          </div>
          <p>{{ t(`console.s.${active.key}.sub`) }}</p>
        </div>

        <SubTabs v-model="subTab" :tabs="subTabs" />

        <ModuleBoundary :key="active.key + '/' + subTab">
          <component :is="activeComp" />
        </ModuleBoundary>

        <LiveActivityFeed />
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
.nav-item { display: grid; grid-template-columns: 22px 1fr auto; gap: 10px; align-items: center; padding: 10px 12px; border-radius: 10px; color: var(--text-dim); font-size: 14px; }
.nav-item:hover { background: var(--surface); color: var(--text); }
.nav-item.on { background: rgba(124, 92, 255, .15); color: #fff; border: 1px solid rgba(124, 92, 255, .35); padding: 9px 11px; }
.ico { font-size: 16px; }
.cnt { font-size: 10px; padding: 2px 7px; border-radius: 999px; background: var(--surface-2); color: var(--text-dim); font-variant-numeric: tabular-nums; }
.nav-item.on .cnt { background: rgba(124, 92, 255, .3); color: #fff; }
.hint { margin-top: auto; padding: 14px; background: rgba(124, 92, 255, .06); border-color: rgba(124, 92, 255, .25); }
.hint p { margin: 4px 0 12px; font-size: 12px; color: var(--text-dim); }
.btn.sm { padding: 6px 12px; font-size: 12px; justify-content: center; width: 100%; }

.main { min-width: 0; }
.m-head { margin-bottom: 20px; }
.m-title { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.m-head h2 { font-size: 32px; }
.m-head p { margin: 6px 0 0; color: var(--text-dim); }

@media (max-width: 900px) {
  .shell { grid-template-columns: 1fr; }
  .side { position: static; }
  .nav { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
  .hint { display: none; }
}
</style>
