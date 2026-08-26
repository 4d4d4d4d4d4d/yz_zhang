import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createRouter, createMemoryHistory } from 'vue-router'
import en from '../src/i18n/locales/en.js'
import { SECTIONS } from '../src/console/registry.js'
import Console from '../src/views/Console.vue'

beforeAll(() => {
  const g = { addColorStop: () => {} }
  HTMLCanvasElement.prototype.getContext = () => ({
    fillRect: () => {}, clearRect: () => {}, beginPath: () => {}, moveTo: () => {},
    lineTo: () => {}, stroke: () => {}, arc: () => {}, fill: () => {}, save: () => {},
    restore: () => {}, translate: () => {}, scale: () => {}, rotate: () => {},
    createLinearGradient: () => g, createRadialGradient: () => g,
    fillText: () => {}, measureText: () => ({ width: 0 }), setTransform: () => {}, closePath: () => {}
  })
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

const i18n = () => createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const router = () => createRouter({ history: createMemoryHistory(), routes: [
  { path: '/', name: 'home', component: { template: '<div/>' } },
  { path: '/console/:tab?', name: 'console', component: { template: '<div/>' } },
  { path: '/contact', name: 'contact', component: { template: '<div/>' } }
]})

function accessibleName(el) {
  return (el.getAttribute('aria-label') || el.getAttribute('title') ||
    el.getAttribute('aria-labelledby') || el.textContent || '').trim()
}

// Spec 56 — WCAG conformance swept across every console sub-tab. The existing
// a11y test covered one component; the interactive surface has since grown to
// ~50. These are the failures that are statically detectable at mount:
// 4.1.2 Name/Role/Value (unnamed buttons), 3.3.2 Labels or Instructions
// (unlabeled form controls), 2.4.3 Focus Order (positive tabindex), and
// 1.1.1 Non-text Content (images without alt).
describe('console a11y conformance (spec 56)', () => {
  it('every interactive control across every sub-tab is accessible', async () => {
    const findings = { unnamedButton: [], unlabeledControl: [], positiveTabindex: [], imgNoAlt: [] }
    for (const section of SECTIONS) {
      const r = router(); r.push(`/console/${section.key}`); await r.isReady()
      const w = mount(Console, { global: { plugins: [i18n(), r] }, attachTo: document.body })
      const tabs = w.findAll('[role="tab"]')
      for (let i = 0; i < tabs.length; i++) {
        await tabs[i].trigger('click'); await w.vm.$nextTick()
        const root = w.element
        for (const b of root.querySelectorAll('button')) {
          if (!accessibleName(b)) findings.unnamedButton.push(`${section.key}/${i}: ${b.className}`)
        }
        for (const c of root.querySelectorAll('input,select,textarea')) {
          const named = accessibleName(c) || c.closest('label') || (c.id && root.querySelector(`label[for="${c.id}"]`))
          if (!named) findings.unlabeledControl.push(`${section.key}/${i} <${c.tagName.toLowerCase()} type=${c.type} class="${c.className}"> ctx: ${(c.parentElement?.textContent||"").trim().slice(0,50)}`)
        }
        for (const t of root.querySelectorAll('[tabindex]')) {
          if (Number(t.getAttribute('tabindex')) > 0) findings.positiveTabindex.push(`${section.key}/${i}`)
        }
        for (const im of root.querySelectorAll('img')) {
          if (!im.hasAttribute('alt') && im.getAttribute('aria-hidden') !== 'true') findings.imgNoAlt.push(`${section.key}/${i}`)
        }
      }
      w.unmount()
    }
    const report = Object.entries(findings)
      .filter(([, v]) => v.length)
      .map(([k, v]) => `${k} (${v.length}):\n  ${[...new Set(v)].join('\n  ')}`)
      .join('\n')
    expect(findings.unnamedButton, report).toEqual([])
    expect(findings.unlabeledControl, report).toEqual([])
    expect(findings.positiveTabindex, report).toEqual([])
    expect(findings.imgNoAlt, report).toEqual([])
  })
})
