<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import SectionHeader from '../components/SectionHeader.vue'
import { CURRENCIES, formatPrice, defaultCurrencyFor } from '../logic/currency.js'
const { t, locale } = useI18n()

const cycle = ref('monthly')
const prices = {
  starter: { monthly: 0,   yearly: 0 },
  growth:  { monthly: 499, yearly: 399 },
  scale:   { monthly: null, yearly: null }
}

// Spec 25: currency defaults from the locale, follows locale switches
// until the visitor overrides manually.
const currency = ref(defaultCurrencyFor(locale.value))
const overridden = ref(false)
watch(locale, l => { if (!overridden.value) currency.value = defaultCurrencyFor(l) })
function pickCurrency(code) { currency.value = code; overridden.value = true }

function price(plan) {
  const v = prices[plan][cycle.value]
  if (v === null) return t('pricing.custom')
  if (v === 0) return t('pricing.free')
  return formatPrice(v, currency.value, locale.value)
}
</script>

<template>
  <section class="section">
    <div class="container">
      <SectionHeader :title="t('pricing.title')" :subtitle="t('pricing.subtitle')" />

      <div class="cycle">
        <button :class="{ on: cycle === 'monthly' }" @click="cycle='monthly'" type="button">{{ t('pricing.monthly') }}</button>
        <button :class="{ on: cycle === 'yearly' }" @click="cycle='yearly'" type="button">{{ t('pricing.yearly') }}</button>
      </div>

      <div class="currency">
        <button v-for="(c, code) in CURRENCIES" :key="code" type="button"
          :class="{ on: currency === code }" @click="pickCurrency(code)">{{ code }}</button>
      </div>
      <p class="fx-note">{{ t('pricing.fx', { code: currency }) }}</p>

      <div class="grid grid-3">
        <div class="card plan">
          <div class="tag">{{ t('pricing.starter.tag') }}</div>
          <h3>{{ t('pricing.starter.name') }}</h3>
          <div class="price"><span class="amt">{{ price('starter') }}</span><span class="cycle-unit" v-if="prices.starter[cycle]">{{ t('pricing.perMonth') }}</span></div>
          <ul>
            <li v-for="k in ['f1','f2','f3','f4']" :key="k">{{ t(`pricing.starter.${k}`) }}</li>
          </ul>
          <router-link to="/contact" class="btn btn-ghost">{{ t('pricing.cta') }}</router-link>
        </div>
        <div class="card plan featured">
          <div class="ribbon">Popular</div>
          <div class="tag">{{ t('pricing.growth.tag') }}</div>
          <h3>{{ t('pricing.growth.name') }}</h3>
          <div class="price"><span class="amt grad-text">{{ price('growth') }}</span><span class="cycle-unit">{{ t('pricing.perMonth') }}</span></div>
          <ul>
            <li v-for="k in ['f1','f2','f3','f4','f5']" :key="k">{{ t(`pricing.growth.${k}`) }}</li>
          </ul>
          <router-link to="/contact" class="btn btn-primary">{{ t('pricing.cta') }} →</router-link>
        </div>
        <div class="card plan">
          <div class="tag">{{ t('pricing.scale.tag') }}</div>
          <h3>{{ t('pricing.scale.name') }}</h3>
          <div class="price"><span class="amt">{{ price('scale') }}</span></div>
          <ul>
            <li v-for="k in ['f1','f2','f3','f4','f5']" :key="k">{{ t(`pricing.scale.${k}`) }}</li>
          </ul>
          <router-link to="/contact" class="btn btn-ghost">{{ t('pricing.contactSales') }}</router-link>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.cycle { display: inline-flex; padding: 4px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); margin: 0 auto 32px; gap: 4px; }
.cycle { display: flex; justify-content: center; width: max-content; margin-left: auto; margin-right: auto; margin-bottom: 40px; }
.cycle button { padding: 8px 18px; border-radius: 999px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 13px; font-weight: 600; }
.cycle button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }
.currency { display: flex; justify-content: center; gap: 6px; margin: -24px auto 8px; }
.currency button { padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text-dim); font-size: 11px; font-weight: 700; cursor: pointer; }
.currency button.on { border-color: rgba(124, 92, 255, .55); background: rgba(124, 92, 255, .15); color: #fff; }
.fx-note { text-align: center; font-size: 11px; color: var(--text-dim); margin: 0 0 28px; }

.plan { display: flex; flex-direction: column; gap: 14px; position: relative; }
.plan .tag { font-size: 12px; color: var(--text-dim); }
.price { display: flex; align-items: baseline; gap: 6px; margin: 6px 0 8px; }
.amt { font-size: 36px; font-weight: 800; }
.cycle-unit { color: var(--text-dim); font-size: 14px; }
.plan ul { list-style: none; margin: 0; padding: 0; flex: 1; }
.plan li { padding: 8px 0; border-bottom: 1px dashed var(--border); color: var(--text); font-size: 14px; display: flex; gap: 8px; }
.plan li:last-child { border-bottom: 0; }
.plan li::before { content: '✓'; color: var(--success); font-weight: 700; }
.plan :deep(.btn) { justify-content: center; margin-top: 8px; }

.featured { border-color: rgba(124, 92, 255, .5); background: linear-gradient(180deg, rgba(124,92,255,.1), rgba(34,211,238,.05)); }
.ribbon { position: absolute; top: -10px; right: 20px; padding: 4px 10px; border-radius: 999px; background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
</style>
