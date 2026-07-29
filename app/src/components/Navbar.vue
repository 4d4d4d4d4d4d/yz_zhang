<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import LangSwitcher from './LangSwitcher.vue'
import MotionToggle from './MotionToggle.vue'

const { t } = useI18n()
const open = ref(false)
const links = [
  { to: '/', key: 'nav.home' },
  { to: '/product', key: 'nav.product' },
  { to: '/studio', key: 'nav.studio' },
  { to: '/console', key: 'nav.console' },
  { to: '/cases', key: 'nav.cases' },
  { to: '/pricing', key: 'nav.pricing' },
  { to: '/about', key: 'nav.about' }
]
</script>

<template>
  <header class="nav">
    <div class="container nav-inner">
      <router-link to="/" class="brand" @click="open = false">
        <span class="logo-mark" aria-hidden="true"></span>
        <span class="brand-name">{{ t('brand') }}</span>
      </router-link>
      <button class="burger" :aria-expanded="open" @click="open = !open" aria-label="Menu">
        <span></span><span></span><span></span>
      </button>
      <nav class="links" :class="{ open }">
        <router-link
          v-for="l in links" :key="l.to" :to="l.to"
          class="link" active-class="active"
          :exact-active-class="l.to === '/' ? 'active' : ''"
          @click="open = false"
        >{{ t(l.key) }}</router-link>
        <div class="nav-actions">
          <MotionToggle />
          <LangSwitcher />
          <router-link to="/contact" class="btn btn-primary" @click="open = false">
            {{ t('nav.contact') }}
          </router-link>
        </div>
      </nav>
    </div>
  </header>
</template>

<style scoped>
.nav {
  position: sticky; top: 0; z-index: 50;
  backdrop-filter: blur(14px);
  background: rgba(7, 7, 11, 0.7);
  border-bottom: 1px solid var(--border);
}
.nav-inner { display: flex; align-items: center; justify-content: space-between; padding: 16px 24px; gap: 16px; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 700; letter-spacing: .02em; }
.brand-name { font-size: 18px; }
.logo-mark {
  width: 24px; height: 24px; border-radius: 7px;
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  box-shadow: 0 8px 24px -8px rgba(124, 92, 255, .6);
}
.links { display: flex; align-items: center; gap: 28px; }
.link { color: var(--text-dim); font-size: 15px; padding: 6px 2px; border-bottom: 1px solid transparent; }
.link:hover { color: var(--text); }
.link.active { color: var(--text); border-bottom-color: var(--primary); }
.nav-actions { display: flex; align-items: center; gap: 12px; margin-left: 8px; }
.burger { display: none; background: transparent; border: 1px solid var(--border); border-radius: 10px; padding: 8px; cursor: pointer; }
.burger span { display: block; width: 18px; height: 2px; background: var(--text); margin: 3px 0; }

@media (max-width: 900px) {
  .burger { display: block; }
  .links {
    position: absolute; top: 100%; left: 0; right: 0;
    background: var(--bg-2); border-bottom: 1px solid var(--border);
    flex-direction: column; align-items: stretch; gap: 0;
    transform: translateY(-8px); opacity: 0; pointer-events: none;
    transition: opacity .15s ease, transform .15s ease;
  }
  .links.open { transform: translateY(0); opacity: 1; pointer-events: auto; }
  .link { padding: 14px 24px; border-bottom: 1px solid var(--border); }
  .nav-actions { padding: 14px 24px; flex-direction: column; align-items: stretch; gap: 10px; }
  .nav-actions :deep(.btn) { justify-content: center; }
}
</style>
