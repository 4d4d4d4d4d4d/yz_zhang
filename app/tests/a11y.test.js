import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createRouter, createMemoryHistory } from 'vue-router'
import CommandPalette from '../src/components/CommandPalette.vue'
import { composeTitle } from '../src/composables/useDocumentTitle.js'
import en from '../src/i18n/locales/en.js'

function harness(Comp) {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'home', component: { template: '<div/>' } },
             { path: '/console/:tab?', name: 'console', component: { template: '<div/>' } }]
  })
  return mount(Comp, { global: { plugins: [i18n, router], stubs: { Teleport: true } } })
}

describe('CommandPalette a11y', () => {
  it('exposes dialog + combobox + listbox with aria-selected on the active option', async () => {
    const wrapper = harness(CommandPalette)
    wrapper.vm.open = true
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    const combo = wrapper.find('[role="combobox"]')
    expect(combo.exists()).toBe(true)
    expect(combo.attributes('aria-controls')).toBe('pal-listbox')

    const listbox = wrapper.find('[role="listbox"]')
    expect(listbox.exists()).toBe(true)
    const options = wrapper.findAll('[role="option"]')
    expect(options.length).toBeGreaterThan(0)
    // exactly one option is aria-selected, and the combobox points at it
    const selected = options.filter(o => o.attributes('aria-selected') === 'true')
    expect(selected).toHaveLength(1)
    expect(combo.attributes('aria-activedescendant')).toBe(selected[0].attributes('id'))
  })

  it('announces the result count via an aria-live status node', async () => {
    const wrapper = harness(CommandPalette)
    wrapper.vm.open = true
    await wrapper.vm.$nextTick()
    const live = wrapper.find('[aria-live="polite"]')
    expect(live.exists()).toBe(true)
    expect(live.text()).toMatch(/result/)
  })
})

describe('composeTitle', () => {
  it('joins page and brand', () => {
    expect(composeTitle({ pageTitle: 'Pricing', brand: 'AdForge' })).toBe('Pricing · AdForge')
  })
  it('appends a console section between page and brand', () => {
    expect(composeTitle({ pageTitle: 'Console', section: 'Trust Center', brand: 'AdForge' }))
      .toBe('Console · Trust Center · AdForge')
  })
  it('falls back to brand alone when there is no page title', () => {
    expect(composeTitle({ pageTitle: '', brand: 'AdForge' })).toBe('AdForge')
  })
})
