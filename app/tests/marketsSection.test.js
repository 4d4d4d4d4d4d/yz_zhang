import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

import en from '../src/i18n/locales/en.js'
import zh from '../src/i18n/locales/zh.js'
import ja from '../src/i18n/locales/ja.js'
import es from '../src/i18n/locales/es.js'
import { SECTIONS } from '../src/console/registry.js'
import { GOTO_MAP } from '../src/logic/shortcuts.js'

import MarketEntryScorer from '../src/components/MarketEntryScorer.vue'
import LandedCostPricer from '../src/components/LandedCostPricer.vue'
import MarketReadiness from '../src/components/MarketReadiness.vue'
import RetailCalendar from '../src/components/RetailCalendar.vue'

const LOCALES = { en, zh, ja, es }
const mountIn = (Comp, locale = 'en') => mount(Comp, {
  global: { plugins: [createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: LOCALES })] }
})

beforeAll(() => { vi.spyOn(console, 'warn').mockImplementation(() => {}) })

describe('markets section wiring (spec 60)', () => {
  it('is registered with all four sub-tabs', () => {
    const section = SECTIONS.find(s => s.key === 'markets')
    expect(section).toBeTruthy()
    expect(section.subs).toEqual(['entry', 'landed', 'readiness', 'calendar'])
  })

  it('has a collision-free goto shortcut', () => {
    const keys = Object.keys(GOTO_MAP)
    expect(new Set(keys).size).toBe(keys.length)
    expect(GOTO_MAP.x).toEqual({ name: 'console', params: { tab: 'markets' } })
  })

  it('every sub-tab has a label in all four locales', () => {
    for (const code of Object.keys(LOCALES)) {
      for (const sub of ['entry', 'landed', 'readiness', 'calendar']) {
        expect(LOCALES[code].console.tabs.markets[sub], `${code}/${sub}`).toBeTruthy()
      }
      expect(LOCALES[code].console.s.markets.title, code).toBeTruthy()
    }
  })
})

describe('MarketEntryScorer (spec 60)', () => {
  it('ranks candidates and the weights actually move the ranking', async () => {
    const w = mountIn(MarketEntryScorer)
    const before = w.findAll('.mk-name').map(n => n.text())
    expect(before.length).toBeGreaterThan(3)

    // Kill the distance discount entirely — the biggest, hardest market
    // should climb, which is only possible if the slider feeds the engine.
    await w.findAll('.sl input').at(-1).setValue(0)
    const after = w.findAll('.mk-name').map(n => n.text())
    expect(after).not.toEqual(before)
  })

  it('the reset control appears only once a weight has moved', async () => {
    const w = mountIn(MarketEntryScorer)
    expect(w.find('.list .btn').exists()).toBe(false)
    await w.findAll('.sl input').at(0).setValue(0.5)
    expect(w.find('.list .btn').exists()).toBe(true)
    await w.find('.list .btn').trigger('click')
    expect(w.find('.list .btn').exists()).toBe(false)
  })

  it('the breakdown explains the selected market, and selection changes it', async () => {
    const w = mountIn(MarketEntryScorer)
    const first = w.find('.detail h3').text()
    const rows = w.findAll('.mk')
    await rows.at(rows.length - 1).trigger('click')
    expect(w.find('.detail h3').text()).not.toBe(first)
    // Attractiveness and distance are shown apart, never as one blended number.
    expect(w.findAll('.pt').length).toBe(9) // 5 attractiveness + 4 CAGE
  })

  it('every market row carries a band chip', () => {
    const w = mountIn(MarketEntryScorer)
    const bands = w.findAll('.band').map(b => b.text())
    const known = Object.values(en.entry.band)
    expect(bands.length).toBe(w.findAll('.mk').length)
    for (const b of bands) expect(known).toContain(b)
  })
})

describe('LandedCostPricer (spec 60)', () => {
  it('prices every market and hits the target margin', () => {
    const w = mountIn(LandedCostPricer)
    const rows = w.findAll('.tbl .tr:not(.th)')
    expect(rows.length).toBe(6)
    for (const cell of w.findAll('.mg')) {
      expect(parseFloat(cell.text())).toBeGreaterThanOrEqual(58) // the default target
    }
  })

  it('raising the target margin raises every shelf price', async () => {
    const w = mountIn(LandedCostPricer)
    const priceOf = () => w.findAll('.tbl .tr:not(.th)').map(r => r.findAll('.n').at(3)?.text())
    const before = priceOf()
    await w.findAll('.in input').at(5).setValue(75)
    const after = priceOf()
    expect(after).not.toEqual(before)
  })

  it('charm rounding is optional and only ever helps margin', async () => {
    const w = mountIn(LandedCostPricer)
    const margins = () => w.findAll('.mg').map(m => parseFloat(m.text()))
    const charmed = margins()
    await w.find('.charm input').setValue(false)
    const plain = margins()
    for (let i = 0; i < plain.length; i++) {
      expect(charmed[i]).toBeGreaterThanOrEqual(plain[i] - 0.01)
    }
  })

  it('an impossible target is reported, not rendered as a negative price', async () => {
    const w = mountIn(LandedCostPricer)
    // 99% is merely expensive and still solvable; 100% is the point where no
    // finite price exists. The input allows it precisely so the panel can say
    // so — an operator who types it deserves an answer, not blank cells.
    await w.findAll('.in input').at(5).setValue(99)
    expect(w.findAll('.unreach').length).toBe(0)
    await w.findAll('.in input').at(5).setValue(100)
    expect(w.findAll('.unreach').length).toBe(6)
    expect(w.find('.warnline').exists()).toBe(true)
  })
})

describe('MarketReadiness (spec 60)', () => {
  it('a blocked market cannot rank above a market that can transact', () => {
    const w = mountIn(MarketReadiness)
    const pills = w.findAll('.pill').map(p => p.classes().includes('ok'))
    const firstBlocked = pills.indexOf(false)
    if (firstBlocked !== -1) {
      expect(pills.slice(firstBlocked).every(ok => ok === false)).toBe(true)
    }
  })

  it('blocking and advisory completeness are shown as two numbers, never one', () => {
    const w = mountIn(MarketReadiness)
    expect(w.findAll('.meters .m').length).toBe(2)
    expect(w.text()).toContain(en.golive.blockingGates)
    expect(w.text()).toContain(en.golive.advisoryGates)
  })

  it('selecting a blocked market names its blockers rather than a bare percentage', async () => {
    const w = mountIn(MarketReadiness)
    const blocked = w.findAll('.mk').filter(m => m.classes().includes('blocked'))
    expect(blocked.length).toBeGreaterThan(0)
    await blocked[0].trigger('click')
    const open = w.findAll('.gates li.blocking.open')
    expect(open.length).toBeGreaterThan(0)
    expect(w.find('.detail .meta').text()).not.toBe('')
  })

  it('renders a critical-path line whenever work is outstanding', async () => {
    const w = mountIn(MarketReadiness)
    const blocked = w.findAll('.mk').filter(m => m.classes().includes('blocked'))
    await blocked[0].trigger('click')
    expect(w.find('.cp').exists()).toBe(true)
  })
})

describe('RetailCalendar (spec 60)', () => {
  it('lists the moments inside the window and honours the horizon control', async () => {
    const w = mountIn(RetailCalendar)
    const before = w.findAll('.mrow').length
    expect(before).toBeGreaterThan(0)
    await w.find('.hz select').setValue(365)
    expect(w.findAll('.mrow').length).toBeGreaterThanOrEqual(before)
    await w.find('.hz select').setValue(120)
    expect(w.findAll('.mrow').length).toBeLessThanOrEqual(before)
  })

  it('flags what is late today instead of only drawing a calendar', () => {
    const w = mountIn(RetailCalendar)
    const late = w.findAll('.mrow.late')
    expect(late.length).toBeGreaterThan(0)
    expect(w.find('.alert').exists()).toBe(true)
    for (const row of late) expect(row.find('.run.late').exists()).toBe(true)
  })

  it('the backward plan chains every production stage to the fixed date', async () => {
    const w = mountIn(RetailCalendar)
    const stages = w.findAll('.stages li')
    expect(stages.length).toBe(5)
    expect(w.find('.plan .meta').text()).toContain('25') // total lead days
  })

  it('selecting a different moment re-plans', async () => {
    const w = mountIn(RetailCalendar)
    const first = w.find('.plan h3').text()
    const labels = w.findAll('.mlabel')
    await labels.at(labels.length - 1).trigger('click')
    expect(w.find('.plan h3').text()).not.toBe(first)
  })
})

describe('markets section localization (spec 60)', () => {
  const PANELS = { entry: MarketEntryScorer, landed: LandedCostPricer, readiness: MarketReadiness, calendar: RetailCalendar }

  for (const code of Object.keys(LOCALES)) {
    it(`every panel renders its own copy in ${code}`, () => {
      for (const [key, Comp] of Object.entries(PANELS)) {
        const w = mountIn(Comp, code)
        expect(w.text(), `${key}/${code}`).not.toContain('undefined')
        // A missing key renders as the raw dotted path — catch that directly.
        expect(w.text(), `${key}/${code} has an unresolved i18n key`).not.toMatch(/\b(entry|landed|golive|moments|market)\.[a-zA-Z]+\.?[a-zA-Z]*\b/)
      }
    })
  }

  it('leaves no untranslated English behind in a non-English locale', () => {
    for (const [key, Comp] of Object.entries(PANELS)) {
      const zhText = mountIn(Comp, 'zh').text()
      const markers = {
        entry: en.entry.ranking, landed: en.landed.ladder,
        readiness: en.golive.gates, calendar: en.moments.window
      }
      expect(zhText, key).not.toContain(markers[key])
    }
  })
})
