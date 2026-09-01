import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

import en from '../src/i18n/locales/en.js'
import zh from '../src/i18n/locales/zh.js'
import ja from '../src/i18n/locales/ja.js'
import es from '../src/i18n/locales/es.js'
import TrustCenter from '../src/components/TrustCenter.vue'
import MarketReadiness from '../src/components/MarketReadiness.vue'
import { posture, postureForMarket, MARKET_SCOPE } from '../src/logic/posture.js'

const LOCALES = { en, zh, ja, es }
const mountIn = (Comp, locale = 'en') => mount(Comp, {
  global: { plugins: [createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: LOCALES })] }
})

beforeAll(() => { vi.spyOn(console, 'warn').mockImplementation(() => {}) })

const pickRegion = async (w, region) => {
  const btn = w.findAll('.region button').find(b => b.text() === region)
  await btn.trigger('click')
  return btn
}
const headline = w => w.find('.big').text().replace('/100', '').trim()

describe('TrustCenter · the region filter isolates the region (spec 61)', () => {
  it('Brazil no longer borrows the global framework to look healthy', async () => {
    const w = mountIn(TrustCenter)
    await pickRegion(w, 'BR')
    // Shipped behaviour averaged LGPD (78, caution) with C2PA (100) and
    // reported 89 for the only market flagged caution.
    expect(Number(headline(w))).toBeLessThan(89)
    expect(w.find('.calc strong').text()).toBe('78') // control-weighted, regional only
  })

  it('a global framework is still shown, but marked as not counted here', async () => {
    const w = mountIn(TrustCenter)
    await pickRegion(w, 'BR')
    const ghosts = w.findAll('.fw.ghost')
    expect(ghosts).toHaveLength(1)
    expect(ghosts[0].text()).toContain('C2PA')
    expect(ghosts[0].text()).toContain(en.trustc.globalNote)
    // ...and it is absent from the ghost treatment when the estate is in view.
    await pickRegion(w, 'All')
    expect(w.findAll('.fw.ghost')).toHaveLength(0)
  })

  it('the pass/caution/risk legend counts the region, not the world', async () => {
    const w = mountIn(TrustCenter)
    await pickRegion(w, 'JP')
    // Shipped behaviour printed estate-wide counts beside a regional score.
    expect(w.find('.lg.pass').text()).toContain('1')
    expect(w.find('.lg.risk').text()).toContain('0')
    await pickRegion(w, 'EU')
    expect(w.find('.lg.risk').text()).toContain('1')
  })

  it('open findings are scoped — Brazil is not charged for an EU gap', async () => {
    const w = mountIn(TrustCenter)
    await pickRegion(w, 'BR')
    const rows = w.findAll('.risks tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain(en.trustc.risk.lgpdScc)
  })
})

describe('TrustCenter · a material exception is visible, not averaged (spec 61)', () => {
  it('the EU headline is held down by the AI Act framework and says so', async () => {
    const w = mountIn(TrustCenter)
    await pickRegion(w, 'EU')
    const capLine = w.find('.calc li.cap')
    expect(capLine.exists()).toBe(true)
    expect(capLine.text()).toContain('AI Act')
    // The raw control-weighted number is still shown, so the adjustment is
    // arguable rather than hidden.
    const raw = Number(w.findAll('.calc strong')[0].text())
    expect(raw).toBeGreaterThan(Number(headline(w)))
  })

  it('a clean region shows no cap line', async () => {
    const w = mountIn(TrustCenter)
    await pickRegion(w, 'JP')
    expect(w.find('.calc li.cap').exists()).toBe(false)
  })

  it('the headline matches the engine for every region', async () => {
    const w = mountIn(TrustCenter)
    for (const region of ['All', 'EU', 'US', 'JP', 'BR', 'SEA']) {
      await pickRegion(w, region)
      const scope = region === 'All' ? 'all' : region
      const expected = posture(
        [
          { name: 'GDPR', region: 'EU', status: 'pass', controls: 142, score: 96 },
          { name: 'CCPA / CPRA', region: 'US', status: 'pass', controls: 88, score: 94 },
          { name: 'APPI', region: 'JP', status: 'pass', controls: 64, score: 92 },
          { name: 'LGPD', region: 'BR', status: 'warn', controls: 71, score: 78 },
          { name: 'PDPA', region: 'SEA', status: 'pass', controls: 58, score: 89 },
          { name: 'DSA', region: 'EU', status: 'warn', controls: 47, score: 81 },
          { name: 'C2PA provenance', region: 'all', status: 'pass', controls: 12, score: 100 },
          { name: 'AI Act readiness', region: 'EU', status: 'risk', controls: 38, score: 64 }
        ],
        {
          scope,
          risks: [
            { key: 'lgpdScc', sev: 'high', scope: 'BR' }, { key: 'aiAct', sev: 'high', scope: 'EU' },
            { key: 'dsaFlag', sev: 'med', scope: 'EU' }, { key: 'ccpaOpt', sev: 'med', scope: 'US' },
            { key: 'appiTrn', sev: 'low', scope: 'JP' }
          ]
        }
      )
      expect(Number(headline(w)), region).toBe(expected.score)
    }
  })
})

describe('TrustCenter · the AI review is derived (spec 61)', () => {
  // Regression: the scan returned a fixed 78 and the same five sentences no
  // matter what was on screen — a claim about analysis that never happened.
  it('the scan agrees with the posture on screen and moves with the region', async () => {
    const w = mountIn(TrustCenter)
    await pickRegion(w, 'EU')
    await w.find('.btn-primary').trigger('click')
    await new Promise(r => setTimeout(r, 800))
    await flushPromises()

    const euScore = w.find('.ss-score').text()
    expect(euScore).toBe(headline(w))
    expect(euScore).not.toBe('78')
    const euText = w.find('.scan ul').text()
    expect(euText).toContain('AI Act')

    await pickRegion(w, 'JP')
    await w.find('.btn-primary').trigger('click')
    await new Promise(r => setTimeout(r, 800))
    await flushPromises()
    expect(w.find('.ss-score').text()).toBe(headline(w))
    expect(w.find('.scan ul').text()).not.toBe(euText)
  })

  it('a scope with nothing outstanding says so instead of inventing findings', async () => {
    const w = mountIn(TrustCenter)
    await pickRegion(w, 'SEA')
    await w.find('.btn-primary').trigger('click')
    await new Promise(r => setTimeout(r, 800))
    await flushPromises()
    const items = w.findAll('.scan li')
    expect(items.length).toBeGreaterThan(0)
    expect(w.find('.scan ul').text()).not.toContain(en.trustc.risk.lgpdScc)
  })
})

// The point of spec 61: two surfaces that answer "is this market ready?" must
// not answer it differently.
describe('posture is consistent across surfaces (spec 61)', () => {
  const FW = [
    { name: 'GDPR', region: 'EU', status: 'pass', controls: 142, score: 96 },
    { name: 'APPI', region: 'JP', status: 'pass', controls: 64, score: 92 },
    { name: 'LGPD', region: 'BR', status: 'warn', controls: 71, score: 78 },
    { name: 'PDPA', region: 'SEA', status: 'pass', controls: 58, score: 89 },
    { name: 'DSA', region: 'EU', status: 'warn', controls: 47, score: 81 },
    { name: 'C2PA provenance', region: 'all', status: 'pass', controls: 12, score: 100 },
    { name: 'AI Act readiness', region: 'EU', status: 'risk', controls: 38, score: 64 }
  ]

  it('the market panel reports the same score the Trust Center does', async () => {
    const trust = mountIn(TrustCenter)
    const markets = mountIn(MarketReadiness)

    // Germany is governed by the EU regime; both surfaces must agree.
    await pickRegion(trust, 'EU')
    const de = markets.findAll('.mk').find(m => m.text().includes(en.market.DE))
    await de.trigger('click')
    expect(markets.find('.p-score').text()).toBe(headline(trust))
  })

  it('a market with no regime in scope says so rather than showing a clean score', async () => {
    const w = mountIn(MarketReadiness)
    for (const code of ['AE', 'MX']) {
      expect(MARKET_SCOPE[code]).toBeNull()
      const row = w.findAll('.mk').find(m => m.text().includes(en.market[code]))
      await row.trigger('click')
      expect(w.find('.p-none').exists(), code).toBe(true)
      expect(w.find('.p-score').exists(), code).toBe(false)
    }
  })

  it('a capped market carries the explanation into the market panel too', async () => {
    const w = mountIn(MarketReadiness)
    const de = w.findAll('.mk').find(m => m.text().includes(en.market.DE))
    await de.trigger('click')
    expect(postureForMarket('DE', FW).capped).toBe(true)
    expect(w.find('.p-cap').exists()).toBe(true)
    expect(w.find('.p-cap').text()).toContain('AI Act')
  })
})

describe('TrustCenter · localization (spec 61)', () => {
  for (const code of Object.keys(LOCALES)) {
    it(`renders its own copy in ${code}`, () => {
      const w = mountIn(TrustCenter, code)
      expect(w.text()).toContain(LOCALES[code].trustc.activeRisks)
      expect(w.text()).toContain(LOCALES[code].trustc.docs)
      expect(w.text()).not.toMatch(/\btrustc\.[a-zA-Z]/)
    })
  }

  it('leaves no untranslated English in a non-English locale', () => {
    const w = mountIn(TrustCenter, 'ja')
    for (const marker of [en.trustc.activeRisks, en.trustc.docs, en.trustc.auditLog, en.trustc.runScan]) {
      expect(w.text()).not.toContain(marker)
    }
  })
})
