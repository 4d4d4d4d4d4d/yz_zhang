import { createI18n } from 'vue-i18n'
import en from './locales/en.js'
import zh from './locales/zh.js'
import ja from './locales/ja.js'
import es from './locales/es.js'

const KEY = 'adforge.locale'
const supported = ['en', 'zh', 'ja', 'es']

function detect() {
  if (typeof localStorage !== 'undefined') {
    const saved = localStorage.getItem(KEY)
    if (saved && supported.includes(saved)) return saved
  }
  const nav = (typeof navigator !== 'undefined' && navigator.language) || 'en'
  const short = nav.toLowerCase().split('-')[0]
  if (supported.includes(short)) return short
  return 'en'
}

export const i18n = createI18n({
  legacy: false,
  locale: detect(),
  fallbackLocale: 'en',
  messages: { en, zh, ja, es }
})

export function setLocale(loc) {
  if (!supported.includes(loc)) return
  i18n.global.locale.value = loc
  if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, loc)
  if (typeof document !== 'undefined') document.documentElement.lang = loc
}

export const locales = [
  { code: 'en', label: 'English' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
  { code: 'es', label: 'Español' }
]
