import { describe, it, expect, beforeAll, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createRouter, createMemoryHistory } from 'vue-router'

import en from '../src/i18n/locales/en.js'
import zh from '../src/i18n/locales/zh.js'
import ja from '../src/i18n/locales/ja.js'
import es from '../src/i18n/locales/es.js'
import { SECTIONS } from '../src/console/registry.js'
import { loadSection } from '../src/console/panels.js'

import Console from '../src/views/Console.vue'
import Home from '../src/views/Home.vue'
import Product from '../src/views/Product.vue'
import Studio from '../src/views/Studio.vue'
import Cases from '../src/views/Cases.vue'
import Pricing from '../src/views/Pricing.vue'
import About from '../src/views/About.vue'
import Contact from '../src/views/Contact.vue'

// happy-dom has no canvas 2D context; components that draw (VideoHero)
// guard on it, but stub it so a null return never throws mid-mount.
beforeAll(async () => {
  // Spec 59 — warm every section chunk so a cached panel resolves in a
  // microtask; chunk-loading itself is covered by tests/consolePanels.test.js.
  await Promise.all(SECTIONS.map(s => loadSection(s.key)))

  const gradient = { addColorStop: () => {} }
  HTMLCanvasElement.prototype.getContext = () => ({
    fillRect: () => {}, clearRect: () => {}, beginPath: () => {}, moveTo: () => {},
    lineTo: () => {}, stroke: () => {}, arc: () => {}, fill: () => {}, save: () => {},
    restore: () => {}, translate: () => {}, scale: () => {}, rotate: () => {},
    createLinearGradient: () => gradient, createRadialGradient: () => gradient,
    fillText: () => {}, measureText: () => ({ width: 0 }), setTransform: () => {}, closePath: () => {}
  })
})

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en, zh, ja, es } })
}

function makeRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div/>' } },
      { path: '/console/:tab?', name: 'console', component: { template: '<div/>' } },
      { path: '/contact', name: 'contact', component: { template: '<div/>' } }
    ]
  })
  return router
}

let errors = []
beforeAll(() => {
  vi.spyOn(console, 'error').mockImplementation((...a) => { errors.push(a.join(' ')) })
  vi.spyOn(console, 'warn').mockImplementation((...a) => {
    const s = a.join(' ')
    // ignore benign vue-router "no match" noise for stub routes
    if (!/No match found|router/i.test(s)) errors.push(s)
  })
})
afterEach(() => { errors = [] })

async function mountView(Comp) {
  const router = makeRouter()
  router.push('/')
  await router.isReady()
  const wrapper = mount(Comp, { global: { plugins: [makeI18n(), router] } })
  return wrapper
}

describe('marketing views mount clean', () => {
  const views = { Home, Product, Studio, Cases, Pricing, About, Contact }
  for (const [name, Comp] of Object.entries(views)) {
    it(`${name} mounts without error`, async () => {
      const wrapper = await mountView(Comp)
      expect(wrapper.html().length).toBeGreaterThan(0)
      wrapper.unmount()
      expect(errors, `${name}: ${errors.join(' | ')}`).toEqual([])
    })
  }
})

describe('console — every section and sub-tab mounts clean', () => {
  for (const section of SECTIONS) {
    it(`section "${section.key}" mounts all ${section.subs.length} sub-tabs`, async () => {
      const router = makeRouter()
      router.push(`/console/${section.key}`)
      await router.isReady()
      const wrapper = mount(Console, { global: { plugins: [makeI18n(), router] } })

      // click through every sub-tab so each section component actually mounts
      const buttons = wrapper.findAll('.subtabs button, .tabs button, [role="tab"]')
      expect(buttons.length, `${section.key} sub-tab buttons`).toBe(section.subs.length)
      for (let i = 0; i < buttons.length; i++) {
        await buttons[i].trigger('click')
        await flushPromises(); await wrapper.vm.$nextTick(); await flushPromises()
        // Spec 59 — panels are async. Asserting "no errors" against a panel
        // that never mounted is a test that cannot fail, so require the panel
        // to have actually rendered before believing the silence.
        const panel = wrapper.find('.panel')
        expect(panel.exists(), `${section.key}/${section.subs[i]} panel missing`).toBe(true)
        expect(panel.find('.sk[aria-busy="true"]').exists(), `${section.key}/${section.subs[i]} stuck on skeleton`).toBe(false)
        expect(panel.element.children.length, `${section.key}/${section.subs[i]} rendered empty`).toBeGreaterThan(0)
      }
      wrapper.unmount()
      expect(errors, `${section.key}: ${errors.join(' | ')}`).toEqual([])
    })
  }
})
