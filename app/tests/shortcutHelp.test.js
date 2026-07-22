import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ShortcutHelp from '../src/components/ShortcutHelp.vue'
import { GOTO_MAP } from '../src/logic/shortcuts.js'
import en from '../src/i18n/locales/en.js'

function make() {
  const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
  return mount(ShortcutHelp, { global: { plugins: [i18n] }, attachTo: document.body })
}

function press(key) {
  window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
}

afterEach(() => { document.body.innerHTML = '' })

describe('ShortcutHelp — the `?` cheat-sheet', () => {
  it('is closed until `?` is pressed', async () => {
    const w = make()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    press('?')
    await w.vm.$nextTick()
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    w.unmount()
  })

  it('lists one goto row per GOTO_MAP key plus the global rows', async () => {
    const w = make()
    press('?')
    await w.vm.$nextTick()
    const kbds = document.querySelectorAll('[role="dialog"] .sh-keys')
    // 3 global rows + one row per goto entry
    expect(kbds.length).toBe(3 + Object.keys(GOTO_MAP).length)
    w.unmount()
  })

  it('Escape closes it again', async () => {
    const w = make()
    press('?')
    await w.vm.$nextTick()
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    press('Escape')
    await w.vm.$nextTick()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    w.unmount()
  })

  it('does not open while typing in a field', async () => {
    const w = make()
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.dispatchEvent(new KeyboardEvent('keydown', { key: '?', bubbles: true }))
    await w.vm.$nextTick()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    w.unmount()
  })
})
