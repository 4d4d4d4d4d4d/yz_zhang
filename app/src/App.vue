<script setup>
import { useI18n } from 'vue-i18n'
import Navbar from './components/Navbar.vue'
import Footer from './components/Footer.vue'
import CommandPalette from './components/CommandPalette.vue'
import GotoShortcuts from './components/GotoShortcuts.vue'
import ShortcutHelp from './components/ShortcutHelp.vue'
import ConsentBanner from './components/ConsentBanner.vue'
import { useDocumentTitle } from './composables/useDocumentTitle.js'

const { t } = useI18n()
useDocumentTitle()
</script>

<template>
  <a class="skip-link" href="#main">{{ t('nav.skip') }}</a>
  <Navbar />
  <CommandPalette />
  <GotoShortcuts />
  <ShortcutHelp />
  <main id="main" tabindex="-1">
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <!-- Single-element keyed wrapper: views are multi-root, and a
             transition child must have one element root or in-app
             navigation renders blank (spec 23 R1). Keyed by route NAME so
             /console/:tab switches don't remount the console shell. -->
        <div :key="String($route.name)">
          <component :is="Component" />
        </div>
      </transition>
    </router-view>
  </main>
  <Footer />
  <ConsentBanner />
</template>

<style scoped>
.skip-link {
  position: fixed; top: -60px; left: 12px; z-index: 100;
  padding: 10px 16px; border-radius: 10px;
  background: var(--primary); color: #fff; font-size: 13px; font-weight: 700;
  transition: top .15s;
}
.skip-link:focus { top: 12px; outline: 2px solid #fff; outline-offset: 2px; }
main:focus { outline: none; }
</style>
