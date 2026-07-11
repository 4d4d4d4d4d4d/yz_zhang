import { describe, it, expect } from 'vitest'
import { buildIndex, searchModules, scoreEntry } from '../src/logic/search.js'
import { SECTIONS } from '../src/console/registry.js'
import en from '../src/i18n/locales/en.js'
import zh from '../src/i18n/locales/zh.js'

// Label resolver backed by a real locale catalog (injected — the logic
// layer never imports vue-i18n; spec 24 / spec 22 isolation).
const resolverFor = catalog => (kind, path) => {
  if (kind === 'section') return catalog.console.s[path].title
  const [section, sub] = path.split('.')
  return catalog.console.tabs[section][sub]
}

const enIndex = buildIndex(SECTIONS, resolverFor(en))
const zhIndex = buildIndex(SECTIONS, resolverFor(zh))

describe('buildIndex', () => {
  it('indexes every section and sub-tab from the registry', () => {
    const sections = SECTIONS.length
    const subs = SECTIONS.reduce((s, x) => s + x.subs.length, 0)
    expect(enIndex).toHaveLength(sections + subs)
  })

  it('sub entries carry a ?sub= route and raw keys in the haystack', () => {
    const revrec = enIndex.find(e => e.id === 'deals/revrec')
    expect(revrec.route).toEqual({ name: 'console', params: { tab: 'deals' }, query: { sub: 'revrec' } })
    expect(revrec.haystack).toContain('revrec')
    expect(revrec.haystack).toContain('deals')
  })
})

describe('scoring order', () => {
  const entry = { label: 'Live bandit', haystack: 'live bandit ai recommendations bandit recommend' }

  it('exact > prefix > word-prefix > substring > subsequence', () => {
    expect(scoreEntry('live bandit', entry)).toBe(100)
    expect(scoreEntry('live', entry)).toBe(80)
    expect(scoreEntry('bandit', entry)).toBe(70)
    expect(scoreEntry('ve band', entry)).toBe(50)
    expect(scoreEntry('lbd', entry)).toBe(25)
    expect(scoreEntry('zzz', entry)).toBe(0)
  })
})

describe('searchModules', () => {
  it('finds a module by its English label', () => {
    const hits = searchModules('bandit', enIndex)
    expect(hits[0].id).toBe('recommend/bandit')
  })

  it('finds by raw key even when the label differs', () => {
    const hits = searchModules('revrec', enIndex)
    expect(hits.some(h => h.id === 'deals/revrec')).toBe(true)
  })

  it('matches Chinese labels in the zh index', () => {
    const hits = searchModules('实地调查', zhIndex)
    expect(hits[0].id).toBe('immersive/field')
    expect(searchModules('收入确认', zhIndex)[0].id).toBe('deals/revrec')
  })

  it('empty query returns browse mode (first N, registry order)', () => {
    const hits = searchModules('', enIndex, { limit: 5 })
    expect(hits).toHaveLength(5)
    expect(hits[0].id).toBe(SECTIONS[0].key)
  })

  it('no match returns []; limit is respected', () => {
    expect(searchModules('qqqqqq', enIndex)).toEqual([])
    expect(searchModules('a', enIndex, { limit: 3 })).toHaveLength(3)
  })

  it('section entries route without a sub query', () => {
    const hits = searchModules('video showcase', enIndex)
    const section = hits.find(h => h.sub === null)
    expect(section.route.query).toBeUndefined()
  })
})
