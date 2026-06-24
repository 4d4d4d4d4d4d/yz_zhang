<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import RecommendDeep from '../components/RecommendDeep.vue'
import MarketingHub from '../components/MarketingHub.vue'
import BusinessMatchHub from '../components/BusinessMatchHub.vue'
import DealRoom from '../components/DealRoom.vue'
import TrustCenter from '../components/TrustCenter.vue'

const { t } = useI18n()
const route = useRoute()

const sections = [
  { key: 'recommend', icon: '🧠', titleKey: 'console.s.recommend.title', subKey: 'console.s.recommend.sub', comp: RecommendDeep },
  { key: 'marketing', icon: '📈', titleKey: 'console.s.marketing.title', subKey: 'console.s.marketing.sub', comp: MarketingHub },
  { key: 'partners',  icon: '🤝', titleKey: 'console.s.partners.title',  subKey: 'console.s.partners.sub',  comp: BusinessMatchHub },
  { key: 'deals',     icon: '📝', titleKey: 'console.s.deals.title',     subKey: 'console.s.deals.sub',     comp: DealRoom },
  { key: 'trust',     icon: '🛡', titleKey: 'console.s.trust.title',     subKey: 'console.s.trust.sub',     comp: TrustCenter }
]

const active = computed(() => sections.find(s => s.key === route.params.tab) || sections[0])
</script>

<template>
  <section class="console section--tight">
    <div class="container shell">
      <aside class="side card">
        <div class="ws">
          <div class="ws-logo">A</div>
          <div>
            <div class="ws-name">AdForge Workspace</div>
            <div class="ws-org">Lumi DTC · Pro</div>
          </div>
        </div>
        <div class="kicker">Modules</div>
        <nav class="nav">
          <router-link v-for="s in sections" :key="s.key"
            :to="{ name: 'console', params: { tab: s.key } }"
            class="nav-item" :class="{ on: active.key === s.key }">
            <span class="ico">{{ s.icon }}</span>
            <span>{{ t(s.titleKey) }}</span>
          </router-link>
        </nav>
        <div class="hint card">
          <div class="kicker">Need help?</div>
          <p>Talk to a partner manager — typically replies within 1 business day.</p>
          <router-link to="/contact" class="btn btn-ghost sm">{{ t('cta.contact') }}</router-link>
        </div>
      </aside>

      <main class="main">
        <div class="m-head">
          <h2 class="grad-text">{{ t(active.titleKey) }}</h2>
          <p>{{ t(active.subKey) }}</p>
        </div>
        <component :is="active.comp" :key="active.key" />
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
.m-head { margin-bottom: 24px; }
.m-head h2 { font-size: 32px; }
.m-head p { margin: 6px 0 0; color: var(--text-dim); }

@media (max-width: 900px) {
  .shell { grid-template-columns: 1fr; }
  .side { position: static; }
  .nav { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
  .hint { display: none; }
}
</style>
