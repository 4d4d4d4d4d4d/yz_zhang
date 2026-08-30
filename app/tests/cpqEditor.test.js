import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

import en from '../src/i18n/locales/en.js'
import zh from '../src/i18n/locales/zh.js'
import ja from '../src/i18n/locales/ja.js'
import es from '../src/i18n/locales/es.js'
import CPQEditor from '../src/components/CPQEditor.vue'
import { APPROVAL_TIERS } from '../src/logic/cpq.js'

const LOCALES = { en, zh, ja, es }

function mountCpq(locale = 'en') {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: LOCALES })
  return mount(CPQEditor, { global: { plugins: [i18n] } })
}

// The discount input for a given line index — the lever the whole surface hangs on.
const discountInput = (w, i) => w.findAll('.ln input.num').at(i * 2 + 1)

describe('CPQEditor · approval bar (spec 58)', () => {
  it('draws its zones from the same tier table that routes the approval', () => {
    const w = mountCpq()
    const zones = w.findAll('.ap-zone')
    expect(zones).toHaveLength(APPROVAL_TIERS.length)
    // The captions under the bar are the real thresholds, not a hardcoded copy
    // that can drift when a threshold moves.
    expect(zones.map(z => z.attributes('data-z'))).toEqual(['0–5%', '5–15%', '15–25%', '25%+'])
  })

  it('marker and heading never disagree about who approves', async () => {
    const w = mountCpq()
    const width = 100 / APPROVAL_TIERS.length
    for (const discount of [0, 8, 20, 45]) {
      for (let i = 0; i < w.findAll('.ln').length; i++) {
        await discountInput(w, i).setValue(discount)
      }
      const heading = w.find('.approval h3').text()
      const left = parseFloat(w.find('.ap-marker').attributes('style').match(/left:\s*([\d.]+)%/)[1])
      const column = Math.min(APPROVAL_TIERS.length - 1, Math.floor(left / width))
      expect(heading).toBe(en.cpq.tier[APPROVAL_TIERS[column].key])
    }
  })
})

describe('CPQEditor · margin alert (spec 58)', () => {
  it('is absent while the quote clears the margin floor', async () => {
    const w = mountCpq()
    for (let i = 0; i < w.findAll('.ln').length; i++) await discountInput(w, i).setValue(0)
    expect(w.find('.ap-alert').exists()).toBe(false)
  })

  // Regression: the alert used to be one fixed sentence naming the GPU bundle
  // and the numbers 4% / 52% regardless of what the rep had configured.
  it('names the line it is actually talking about and moves with the quote', async () => {
    const w = mountCpq()
    // Max out every subscription discount: this fixture only dips under the
    // 50% floor when it is genuinely being given away.
    for (const i of [0, 1, 2, 3]) await discountInput(w, i).setValue(60)
    await discountInput(w, 4).setValue(0)

    const first = w.find('.ap-alert')
    expect(first.exists()).toBe(true)
    // Deepest discount wins the tie on gross, and that is the platform line —
    // not the GPU bundle the old hardcoded sentence always blamed.
    const platform = w.findAll('.ln select').at(0).element
    const productName = platform.options[platform.selectedIndex].text
    expect(first.text()).toContain(productName)
    expect(first.text()).not.toContain('GPU bundle')

    const before = first.text()
    await discountInput(w, 4).setValue(20)
    const after = w.find('.ap-alert')
    expect(after.exists()).toBe(true)
    expect(after.text()).not.toBe(before)
  })

  it('renders the shortfall wording only when there is a shortfall', async () => {
    const w = mountCpq()
    for (const i of [0, 1, 2, 3]) await discountInput(w, i).setValue(60)
    const alert = w.find('.ap-alert')
    expect(alert.exists()).toBe(true)
    // A recoverable quote gets the actionable sentence, never the dead end.
    expect(alert.text()).toContain(en.cpq.fixAdvice.split('{')[0].trim())
    expect(alert.text()).not.toContain(en.cpq.fixNone.split('{')[0].trim())
  })
})

describe('CPQEditor · localization (spec 58)', () => {
  for (const code of Object.keys(LOCALES)) {
    it(`renders its own copy in ${code}`, () => {
      const w = mountCpq(code)
      const text = w.text()
      expect(text).toContain(LOCALES[code].cpq.lineItems)
      expect(text).toContain(LOCALES[code].cpq.prTcv)
      expect(w.find('.approval h3').text()).toBe(
        LOCALES[code].cpq.tier[APPROVAL_TIERS.find(t => t.key === 'auto').key] ||
        LOCALES[code].cpq.tier.auto
      )
    })
  }

  it('leaves no untranslated English in a non-English locale', () => {
    const w = mountCpq('zh')
    for (const marker of [en.cpq.lineItems, en.cpq.addItem, en.cpq.prTcv, en.cpq.saveDraft]) {
      expect(w.text()).not.toContain(marker)
    }
  })
})
