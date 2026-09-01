import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join, dirname, basename } from 'node:path'
import { fileURLToPath } from 'node:url'

// Spec 57 — the product sells four-locale operation, but the console it sells
// is largely hardcoded English: 803 user-visible strings across 72 components
// at the time of measurement. Translating that in one pass is not credible, so
// this is a RATCHET: the debt may shrink, never grow. Migrating UsageMetering
// took it to 779, RiskHeatmap to 744, CPQEditor to 712, TrustCenter to 695.
// Migrating a component
// lowers TOTAL_BUDGET; adding an English string to a migrated component fails
// outright.

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

// Components fully migrated to i18n. These must stay at zero.
const MIGRATED = ['UsageMetering.vue', 'RiskHeatmap.vue', 'CPQEditor.vue', 'TrustCenter.vue']

// Ceiling for everything else. Lower this as components migrate; never raise it.
const TOTAL_BUDGET = 695

function templateOf(src) {
  const m = src.match(/<template>([\s\S]*?)<\/template>\s*(?:<style|$)/)
  return m ? m[1] : ''
}

// User-visible literals: text nodes and the attributes a person actually reads.
export function hardcodedStrings(src) {
  const tpl = templateOf(src).replace(/<!--[\s\S]*?-->/g, '')
  const hits = []
  for (const [, text] of tpl.matchAll(/>([^<>{}]{3,})</g)) {
    if (/[A-Za-z]{3,}/.test(text) && text.trim()) hits.push(text.trim())
  }
  // Bound attributes (:title="t(...)") are already dynamic — the lookbehind
  // keeps them out, otherwise a correctly localized attribute reads as debt.
  for (const [, attr] of tpl.matchAll(/(?<![:\w-])(?:placeholder|title|aria-label)="([^"{}]{3,})"/g)) {
    if (/[A-Za-z]{3,}/.test(attr)) hits.push(attr)
  }
  return hits
}

const files = ['src/components', 'src/views'].flatMap(dir =>
  readdirSync(join(ROOT, dir))
    .filter(f => f.endsWith('.vue'))
    .map(f => ({ name: basename(f), path: join(ROOT, dir, f) }))
)

describe('i18n debt ratchet (spec 57)', () => {
  const counts = files.map(f => ({ ...f, hits: hardcodedStrings(readFileSync(f.path, 'utf8')) }))

  for (const name of MIGRATED) {
    it(`${name} stays fully localized`, () => {
      const entry = counts.find(c => c.name === name)
      expect(entry, `${name} not found — update MIGRATED`).toBeTruthy()
      expect(entry.hits, `${name} regressed to hardcoded English:\n  ${entry.hits.join('\n  ')}`).toEqual([])
    })
  }

  it('total hardcoded strings do not grow', () => {
    const total = counts.reduce((s, c) => s + c.hits.length, 0)
    const worst = counts
      .filter(c => c.hits.length)
      .sort((a, b) => b.hits.length - a.hits.length)
      .slice(0, 5)
      .map(c => `${c.name}: ${c.hits.length}`)
      .join(', ')
    expect(
      total,
      `i18n debt is ${total}, budget ${TOTAL_BUDGET}. Worst offenders — ${worst}. ` +
      'Migrate a component and lower TOTAL_BUDGET; never raise it.'
    ).toBeLessThanOrEqual(TOTAL_BUDGET)
  })
})
