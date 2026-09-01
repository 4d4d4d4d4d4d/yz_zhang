<script setup>
import { useI18n } from 'vue-i18n'
import { setConsent } from '../store/workspace.js'
const { t } = useI18n()
const year = new Date().getFullYear()

// Spec 41 — re-open the consent banner so a visitor can withdraw or change
// their choice as easily as they gave it (GDPR).
function managePrivacy() { setConsent({ analytics: false, decided: false }) }
</script>

<template>
  <footer class="foot">
    <div class="container foot-inner">
      <div class="foot-brand">
        <div class="brand-row">
          <span class="logo-mark"></span>
          <span class="brand-name">{{ t('brand') }}</span>
        </div>
        <p class="tagline">{{ t('footer.tagline') }}</p>
      </div>
      <div class="cols">
        <div>
          <h4>{{ t('footer.product') }}</h4>
          <router-link to="/product">{{ t('nav.product') }}</router-link>
          <router-link to="/studio">{{ t('nav.studio') }}</router-link>
          <router-link to="/console">{{ t('nav.console') }}</router-link>
          <router-link to="/pricing">{{ t('nav.pricing') }}</router-link>
        </div>
        <div>
          <h4>{{ t('footer.company') }}</h4>
          <router-link to="/about">{{ t('nav.about') }}</router-link>
          <router-link to="/cases">{{ t('nav.cases') }}</router-link>
          <router-link to="/contact">{{ t('nav.contact') }}</router-link>
        </div>
        <div>
          <h4>{{ t('footer.legal') }}</h4>
          <a href="#">{{ t('footer.privacy') }}</a>
          <a href="#">{{ t('footer.terms') }}</a>
          <a href="#">{{ t('footer.security') }}</a>
        </div>
      </div>
    </div>
    <div class="container copy">
      © {{ year }} {{ t('brand') }}. {{ t('footer.rights') }}
      <button type="button" class="privacy-link" @click="managePrivacy">{{ t('consent.manage') }}</button>
    </div>
  </footer>
</template>

<style scoped>
.foot { border-top: 1px solid var(--border); margin-top: 80px; padding: 56px 0 24px; background: linear-gradient(180deg, transparent, rgba(124, 92, 255, .04)); }
.foot-inner { display: grid; grid-template-columns: 1.2fr 2fr; gap: 48px; }
.brand-row { display: flex; align-items: center; gap: 10px; font-weight: 700; }
.logo-mark { width: 22px; height: 22px; border-radius: 6px; background: linear-gradient(135deg, var(--primary), var(--primary-2)); }
.tagline { color: var(--text-dim); margin: 12px 0 0; max-width: 280px; }
.cols { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
.cols h4 { font-size: 13px; text-transform: uppercase; letter-spacing: .1em; color: var(--text-dim); margin: 0 0 12px; font-weight: 600; }
.cols a { display: block; color: var(--text); padding: 4px 0; font-size: 14px; }
.cols a:hover { color: var(--primary-2); }
.copy { color: var(--text-dim); font-size: 13px; padding-top: 32px; margin-top: 32px; border-top: 1px solid var(--border); }
.privacy-link { background: none; border: 0; color: var(--text-dim); font: inherit; cursor: pointer; text-decoration: underline; margin-left: 12px; padding: 0; }
.privacy-link:hover { color: var(--primary-2); }

@media (max-width: 900px) {
  .foot-inner { grid-template-columns: 1fr; gap: 32px; }
  .cols { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 600px) {
  .cols { grid-template-columns: 1fr 1fr; }
}
</style>
