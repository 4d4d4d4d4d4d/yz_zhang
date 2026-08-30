import { createI18n } from 'vue-i18n'
import en from './locales/en.js'

// Spec 58 — locales are code-split. Only the fallback (`en`) is bundled with
// the app; the rest are fetched on demand. Shipping all four eagerly put every
// translated string into the entry chunk, so paying down i18n debt made the
// first paint heavier — a quality guard fighting a performance guard. This
// keeps the two pulling the same way: migrating a component now costs bytes
// only in the locale the reader actually asked for.
const loaders = {
  zh: () => import('./locales/zh.js'),
  ja: () => import('./locales/ja.js'),
  es: () => import('./locales/es.js')
}

const KEY = 'adforge.locale'
const supported = ['en', ...Object.keys(loaders)]

function detect() {
  if (typeof localStorage !== 'undefined') {
    try {
      const saved = localStorage.getItem(KEY)
      if (saved && supported.includes(saved)) return saved
    } catch { /* storage blocked — fall through to the navigator */ }
  }
  const nav = (typeof navigator !== 'undefined' && navigator.language) || 'en'
  const short = nav.toLowerCase().split('-')[0]
  return supported.includes(short) ? short : 'en'
}

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en }
})

const inflight = new Map()

// Idempotent: a locale already in the bundle, or already fetched, resolves
// immediately. Concurrent requests for the same locale share one network trip.
export function loadLocale(loc) {
  if (!supported.includes(loc)) return Promise.resolve(false)
  if (i18n.global.availableLocales.includes(loc)) return Promise.resolve(true)
  if (!inflight.has(loc)) {
    inflight.set(loc, loaders[loc]().then(m => {
      i18n.global.setLocaleMessage(loc, m.default)
      return true
    }).catch(() => {
      // A failed chunk must not strand the reader on a blank UI: keep the
      // current locale and let them try again.
      inflight.delete(loc)
      return false
    }))
  }
  return inflight.get(loc)
}

export async function setLocale(loc) {
  if (!supported.includes(loc)) return false
  if (!(await loadLocale(loc))) return false
  i18n.global.locale.value = loc
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, loc)
  } catch { /* storage blocked — the switch still applies for this session */ }
  if (typeof document !== 'undefined') document.documentElement.lang = loc
  return true
}

// Resolve the reader's locale before the first paint so a saved non-English
// preference never flashes English on the way in.
export async function bootstrapI18n() {
  const loc = detect()
  if (loc !== 'en') await setLocale(loc)
  else if (typeof document !== 'undefined') document.documentElement.lang = 'en'
  return i18n
}

export const locales = [
  { code: 'en', label: 'English' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
  { code: 'es', label: 'Español' }
]
