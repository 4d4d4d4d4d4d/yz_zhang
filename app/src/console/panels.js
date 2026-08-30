// Spec 59 — console panels are code-split one chunk per section.
//
// The console used to import all 51 panels eagerly, so opening a single
// section downloaded the other six. That put the Console chunk at 109.34 KB
// gzip against a 110 KB budget: 0.6% of headroom with 68 components still
// queued for i18n migration. Section granularity — rather than one chunk per
// panel — matches how people actually move through the console: they pick a
// section from the sidebar, then flick between its sub-tabs, and those flicks
// must not each cost a network round trip.

const loaders = {
  recommend: () => import('./sections/recommend.js'),
  marketing: () => import('./sections/marketing.js'),
  partners: () => import('./sections/partners.js'),
  deals: () => import('./sections/deals.js'),
  showcase: () => import('./sections/showcase.js'),
  immersive: () => import('./sections/immersive.js'),
  trust: () => import('./sections/trust.js')
}

const cache = new Map()

export const loadableSections = Object.keys(loaders)

// Idempotent and de-duplicated: concurrent callers share one import, and a
// failed load is evicted so a retry can succeed rather than caching the error.
export function loadSection(key) {
  if (!loaders[key]) return Promise.reject(new Error(`Unknown console section: ${key}`))
  if (!cache.has(key)) {
    cache.set(key, loaders[key]().then(m => m.default).catch(err => {
      cache.delete(key)
      throw err
    }))
  }
  return cache.get(key)
}

export function isSectionLoaded(key) {
  return cache.has(key)
}

// Warm a section without caring whether it arrives — used for speculative
// prefetch, where a failure is not the reader's problem.
export function prefetchSection(key) {
  if (!loaders[key]) return Promise.resolve(false)
  return loadSection(key).then(() => true, () => false)
}
