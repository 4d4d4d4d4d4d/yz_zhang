import { describe, it, expect } from 'vitest'
import { createI18n } from 'vue-i18n'
import { baseCompile } from '@intlify/message-compiler'
import en from '../src/i18n/locales/en.js'
import zh from '../src/i18n/locales/zh.js'
import ja from '../src/i18n/locales/ja.js'
import es from '../src/i18n/locales/es.js'

const CATALOGS = { en, zh, ja, es }

// Mirror of Console.vue's section registry (spec 14: drift fails the test).
const CONSOLE_SECTIONS = {
  recommend: ['inputs', 'agents', 'registry', 'bandit', 'features', 'experiments'],
  marketing: ['overview', 'control', 'attribution', 'audience', 'retention', 'forecast'],
  partners:  ['network', 'pipeline', 'intel', 'outreach', 'forecast', 'territory'],
  deals:     ['room', 'playbook', 'workflow', 'library', 'obligations', 'analytics'],
  showcase:  ['gallery', 'links', 'verification', 'pipeline'],
  immersive: ['avatar', 'meeting', 'tour', 'field'],
  trust:     ['posture', 'controls', 'heatmap', 'dpia', 'audit', 'policies']
}

function flattenKeys(obj, prefix = '') {
  const keys = []
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object') keys.push(...flattenKeys(v, path))
    else keys.push(path)
  }
  return keys.sort()
}

describe('key-tree parity across locales', () => {
  const reference = flattenKeys(en)

  for (const locale of ['zh', 'ja', 'es']) {
    it(`${locale} carries exactly the en key tree`, () => {
      const keys = flattenKeys(CATALOGS[locale])
      const missing = reference.filter(k => !keys.includes(k))
      const extra = keys.filter(k => !reference.includes(k))
      expect(missing, `missing in ${locale}: ${missing.join(', ')}`).toEqual([])
      expect(extra, `extra in ${locale}: ${extra.join(', ')}`).toEqual([])
    })
  }
})

describe('message compile safety (@intlify/message-compiler)', () => {
  // The v9 Contact crash regression guard. Note: in dev mode the runtime
  // only *warns* on bad messages — production builds throw — so the guard
  // uses the compiler directly, which reports errors deterministically
  // in every environment.
  function compileErrors(message) {
    const errors = []
    baseCompile(String(message), { onError: e => errors.push(e.message) })
    return errors
  }

  function lookup(catalog, path) {
    return path.split('.').reduce((o, k) => o?.[k], catalog)
  }

  for (const [locale, catalog] of Object.entries(CATALOGS)) {
    it(`every ${locale} message compiles cleanly`, () => {
      const failures = []
      for (const key of flattenKeys(catalog)) {
        for (const err of compileErrors(lookup(catalog, key))) {
          failures.push(`${locale}.${key}: ${err}`)
        }
      }
      expect(failures, failures.join('\n')).toEqual([])
    })
  }

  it('catches the historical unescaped-@ form; escaped form renders the address', () => {
    expect(compileErrors('partners@adforge.ai')).not.toEqual([])
    expect(compileErrors("partners{'@'}adforge.ai")).toEqual([])
    expect(en.contact.email_us).toContain("{'@'}")
    const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
    expect(i18n.global.t('contact.email_us')).toBe('partners@adforge.ai')
  })
})

describe('console shell coverage', () => {
  for (const locale of Object.keys(CATALOGS)) {
    it(`${locale} covers every console section and sub-tab`, () => {
      const cat = CATALOGS[locale]
      for (const [section, subs] of Object.entries(CONSOLE_SECTIONS)) {
        expect(cat.console.s[section]?.title, `${locale} console.s.${section}.title`).toBeTruthy()
        expect(cat.console.s[section]?.sub, `${locale} console.s.${section}.sub`).toBeTruthy()
        for (const sub of subs) {
          expect(cat.console.tabs[section]?.[sub], `${locale} console.tabs.${section}.${sub}`).toBeTruthy()
        }
      }
    })
  }
})
