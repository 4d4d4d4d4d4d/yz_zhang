import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// The i18n instance is a module singleton, so every case gets a fresh module
// graph — otherwise one test's loaded locale silently satisfies the next.
async function freshI18n() {
  vi.resetModules()
  return import('../src/i18n/index.js')
}

const store = {}
beforeEach(() => {
  for (const k of Object.keys(store)) delete store[k]
  vi.stubGlobal('localStorage', {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v) },
    removeItem: k => { delete store[k] }
  })
  vi.stubGlobal('navigator', { language: 'en-US' })
})
afterEach(() => { vi.unstubAllGlobals() })

describe('i18n locale loading (spec 58)', () => {
  it('bundles only the fallback locale', async () => {
    const { i18n } = await freshI18n()
    expect(i18n.global.availableLocales).toEqual(['en'])
    expect(i18n.global.locale.value).toBe('en')
  })

  it('fetches a locale on demand and switches to it', async () => {
    const { i18n, setLocale } = await freshI18n()
    expect(await setLocale('ja')).toBe(true)
    expect(i18n.global.locale.value).toBe('ja')
    expect(i18n.global.availableLocales).toContain('ja')
    // Real messages arrived, not an empty shell that falls through to English.
    expect(i18n.global.t('cpq.lineItems')).not.toBe('Line items')
  })

  it('remembers the choice and restores it before the first paint', async () => {
    const first = await freshI18n()
    await first.setLocale('es')
    expect(store['adforge.locale']).toBe('es')

    const next = await freshI18n()
    expect(next.i18n.global.locale.value).toBe('en') // not yet bootstrapped
    await next.bootstrapI18n()
    expect(next.i18n.global.locale.value).toBe('es')
  })

  it('falls back to the navigator language when nothing is saved', async () => {
    vi.stubGlobal('navigator', { language: 'zh-CN' })
    const { i18n, bootstrapI18n } = await freshI18n()
    await bootstrapI18n()
    expect(i18n.global.locale.value).toBe('zh')
  })

  it('falls back to English for a locale we do not ship', async () => {
    vi.stubGlobal('navigator', { language: 'fr-FR' })
    const { i18n, bootstrapI18n } = await freshI18n()
    await bootstrapI18n()
    expect(i18n.global.locale.value).toBe('en')
  })

  it('a saved preference outranks the navigator language', async () => {
    store['adforge.locale'] = 'es'
    vi.stubGlobal('navigator', { language: 'ja-JP' })
    const { i18n, bootstrapI18n } = await freshI18n()
    await bootstrapI18n()
    expect(i18n.global.locale.value).toBe('es')
  })

  it('rejects an unsupported locale without touching the current one', async () => {
    const { i18n, setLocale, loadLocale } = await freshI18n()
    expect(await setLocale('kl')).toBe(false)
    expect(await loadLocale('kl')).toBe(false)
    expect(i18n.global.locale.value).toBe('en')
  })

  it('shares one fetch between concurrent requests for the same locale', async () => {
    const { loadLocale, i18n } = await freshI18n()
    const results = await Promise.all([loadLocale('zh'), loadLocale('zh'), loadLocale('zh')])
    expect(results).toEqual([true, true, true])
    expect(i18n.global.availableLocales.filter(l => l === 'zh')).toHaveLength(1)
  })

  it('an already-available locale resolves without another fetch', async () => {
    const { loadLocale } = await freshI18n()
    await loadLocale('ja')
    expect(await loadLocale('ja')).toBe(true)
    expect(await loadLocale('en')).toBe(true)
  })

  it('survives storage being blocked in both directions', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => { throw new Error('blocked') },
      setItem: () => { throw new Error('blocked') }
    })
    vi.stubGlobal('navigator', { language: 'ja' })
    const { setLocale, bootstrapI18n, i18n } = await freshI18n()
    await bootstrapI18n()
    expect(i18n.global.locale.value).toBe('ja')
    expect(await setLocale('es')).toBe(true)
    expect(i18n.global.locale.value).toBe('es')
  })

  it('sets the document language so screen readers switch voice', async () => {
    const { setLocale, bootstrapI18n } = await freshI18n()
    await bootstrapI18n()
    expect(document.documentElement.lang).toBe('en')
    await setLocale('zh')
    expect(document.documentElement.lang).toBe('zh')
  })

  it('offers exactly the locales it can actually load', async () => {
    const { locales, loadLocale } = await freshI18n()
    for (const { code } of locales) {
      expect(await loadLocale(code), `${code} is offered but cannot be loaded`).toBe(true)
    }
  })
})
