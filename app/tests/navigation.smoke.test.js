import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createRouter, createMemoryHistory } from 'vue-router'

import en from '../src/i18n/locales/en.js'
import zh from '../src/i18n/locales/zh.js'
import ja from '../src/i18n/locales/ja.js'
import es from '../src/i18n/locales/es.js'
import App from '../src/App.vue'
import Home from '../src/views/Home.vue'
import Product from '../src/views/Product.vue'
import Pricing from '../src/views/Pricing.vue'
import Console from '../src/views/Console.vue'

// Spec 23 R1 discovery — in-app SPA navigation must actually render the
// destination. The broken multi-root <transition> shipped blank pages on
// every navbar click; only full page loads worked, so goto()-style smokes
// never saw it. This mounts the real App and navigates in-app.

beforeAll(() => {
  const gradient = { addColorStop: () => {} }
  HTMLCanvasElement.prototype.getContext = () => ({
    fillRect: () => {}, clearRect: () => {}, beginPath: () => {}, moveTo: () => {},
    lineTo: () => {}, stroke: () => {}, arc: () => {}, fill: () => {}, save: () => {},
    restore: () => {}, translate: () => {}, scale: () => {}, rotate: () => {},
    createLinearGradient: () => gradient, createRadialGradient: () => gradient,
    fillText: () => {}, measureText: () => ({ width: 0 }), setTransform: () => {}, closePath: () => {}
  })
})

function makeApp() {
  const warnings = []
  vi.spyOn(console, 'warn').mockImplementation((...a) => { warnings.push(a.join(' ')) })
  vi.spyOn(console, 'error').mockImplementation((...a) => { warnings.push(a.join(' ')) })

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: Home, meta: { titleKey: 'title.home' } },
      { path: '/product', name: 'product', component: Product, meta: { titleKey: 'title.product' } },
      { path: '/pricing', name: 'pricing', component: Pricing, meta: { titleKey: 'title.pricing' } },
      { path: '/console/:tab?', name: 'console', component: Console, meta: { titleKey: 'title.console' } }
    ]
  })
  const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en, zh, ja, es } })
  const wrapper = mount(App, { global: { plugins: [i18n, router] } })
  return { wrapper, router, warnings }
}

const settle = async (wrapper, ms = 400) => {
  // let the out-in transition finish (fade is .2s)
  await new Promise(r => setTimeout(r, ms))
  await wrapper.vm.$nextTick()
}

describe('transition structure (the browser-only blank-swap guard)', () => {
  // happy-dom has no CSS engine, so the blank-swap itself is only
  // reproducible in a real browser. The durable unit-level guard is the
  // fix contract: the transition's direct child must be a single keyed
  // element wrapper, never the (multi-root) routed component itself.
  it('App.vue wraps the routed component in a keyed single-element child', async () => {
    const { readFileSync } = await import('node:fs')
    const { join, dirname } = await import('node:path')
    const { fileURLToPath } = await import('node:url')
    const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '../src/App.vue'), 'utf8')
    const transitionBlock = src.match(/<transition[\s\S]*?<\/transition>/)?.[0] ?? ''
    expect(transitionBlock, 'transition block exists').not.toBe('')
    expect(transitionBlock, 'child is a keyed <div> wrapper').toMatch(/<div :key=/)
    expect(transitionBlock, 'routed component sits inside the wrapper').toMatch(/<div :key=[\s\S]*<component :is="Component"/)
  })
})

describe('in-app SPA navigation renders every destination', () => {
  it('home → product → pricing → console/showcase all render content', async () => {
    const { wrapper, router, warnings } = makeApp()
    router.push('/')
    await router.isReady()
    await settle(wrapper)
    expect(wrapper.html().length).toBeGreaterThan(2000)

    await router.push('/product')
    await settle(wrapper)
    expect(wrapper.text(), 'product should render the trust journey').toContain('trust journey')

    await router.push('/pricing')
    await settle(wrapper)
    expect(wrapper.text(), 'pricing should render plans').toContain('Starter')
    // spec 28: document.title is localized + route-synced
    expect(document.title).toBe('Pricing · AdForge')

    await router.push('/console/showcase')
    await settle(wrapper)
    expect(wrapper.text(), 'console should render the showcase section').toContain('Video Showcase')

    const vueWarnings = warnings.filter(w => /Vue warn|transition/i.test(w))
    expect(vueWarnings, vueWarnings.join('\n')).toEqual([])
    wrapper.unmount()
  })

  it('console tab switch via route param keeps rendering (no remount blank)', async () => {
    const { wrapper, router } = makeApp()
    router.push('/console/showcase')
    await router.isReady()
    await settle(wrapper)
    await router.push('/console/immersive')
    await settle(wrapper)
    expect(wrapper.text()).toContain('Immersive Suite')
    wrapper.unmount()
  })
})
