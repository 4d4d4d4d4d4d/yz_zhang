import { describe, it, expect } from 'vitest'
import { evaluateBudget, budgetFor, pathCost, BUDGETS, TOTAL_BUDGET, PATHS, SECTION_KEYS, SECTION_BUDGET } from '../src/logic/bundleBudget.js'

describe('budgetFor', () => {
  it('matches by filename prefix, falls back to DEFAULT', () => {
    expect(budgetFor('Console-abc123.js')).toBe(BUDGETS.Console)
    expect(budgetFor('index-xyz.js')).toBe(BUDGETS.index)
    expect(budgetFor('Studio-foo.js')).toBe(BUDGETS.DEFAULT)
  })

  it('gives every console section the same ceiling, so none can outgrow its peers', () => {
    for (const key of SECTION_KEYS) {
      expect(budgetFor(`${key}-hash.js`)).toBe(SECTION_BUDGET)
    }
  })
})

describe('evaluateBudget', () => {
  it('passes when every chunk, the total and every path are within budget', () => {
    const r = evaluateBudget([
      { name: 'Console-a.js', gzipKB: 6 },
      { name: 'index-b.js', gzipKB: 83 },
      { name: 'marketing-c.js', gzipKB: 21 },
      { name: 'Studio-c.js', gzipKB: 5 }
    ])
    expect(r.ok).toBe(true)
    expect(r.violations).toEqual([])
    expect(r.totalKB).toBe(115)
    expect(r.paths.console).toMatchObject({ kb: 110, heaviest: 'marketing' })
  })

  it('flags a chunk over its per-entry budget with the overage', () => {
    const r = evaluateBudget([{ name: 'Console-a.js', gzipKB: 140 }])
    expect(r.ok).toBe(false)
    expect(r.violations[0]).toMatchObject({ name: 'Console-a.js', limit: BUDGETS.Console, overBy: 140 - BUDGETS.Console })
  })

  it('flags a default-bucket chunk that balloons', () => {
    const r = evaluateBudget([{ name: 'Studio-a.js', gzipKB: 55 }])
    expect(r.ok).toBe(false)
    expect(r.violations[0].limit).toBe(BUDGETS.DEFAULT)
  })

  it('flags the total ceiling even when each chunk is individually fine', () => {
    const chunks = Array.from({ length: 10 }, (_, i) => ({ name: `X${i}-a.js`, gzipKB: 39 }))
    const r = evaluateBudget(chunks) // 390 > TOTAL_BUDGET, each < DEFAULT 40
    expect(r.ok).toBe(false)
    expect(r.violations.some(v => v.name === '(total)' && v.limit === TOTAL_BUDGET)).toBe(true)
  })

  it('empty input is trivially ok', () => {
    expect(evaluateBudget([])).toMatchObject({ ok: true, totalKB: 0 })
  })
})

// Spec 59 — the sum of all chunks stopped describing any real visitor once the
// console was split by section. These pin the metric that replaced it.
describe('pathCost', () => {
  const CHUNKS = [
    { name: 'index-a.js', gzipKB: 80 },
    { name: 'Console-b.js', gzipKB: 6 },
    { name: 'recommend-c.js', gzipKB: 17 },
    { name: 'marketing-d.js', gzipKB: 21 },
    { name: 'trust-e.js', gzipKB: 16 }
  ]

  it('charges the heaviest alternative once, not the sum of all of them', () => {
    const c = pathCost(CHUNKS, { include: ['index', 'Console'], worstOf: ['recommend', 'marketing', 'trust'] })
    expect(c.base).toBe(86)
    expect(c.worst).toBe(21)
    expect(c.kb).toBe(107) // not 86 + 17 + 21 + 16
    expect(c.heaviest).toBe('marketing')
  })

  it('sums every chunk sharing a prefix — code-splitting a section must still be charged', () => {
    const c = pathCost([
      { name: 'index-a.js', gzipKB: 80 },
      { name: 'marketing-d.js', gzipKB: 12 },
      { name: 'marketing-extra-e.js', gzipKB: 9 }
    ], { include: ['index'], worstOf: ['marketing'] })
    expect(c.worst).toBe(21)
    expect(c.kb).toBe(101)
  })

  it('a path with no alternatives is just its includes', () => {
    const c = pathCost(CHUNKS, { include: ['index'], worstOf: [] })
    expect(c).toMatchObject({ kb: 80, worst: 0, heaviest: null })
  })

  it('missing chunks cost nothing rather than NaN', () => {
    expect(pathCost([], PATHS.console)).toMatchObject({ kb: 0, heaviest: null })
    expect(pathCost(CHUNKS, {})).toMatchObject({ kb: 0 })
    expect(pathCost()).toMatchObject({ kb: 0 })
  })

  it('reports which section blew the path budget, not just that one did', () => {
    const r = evaluateBudget([
      { name: 'index-a.js', gzipKB: 99 },
      { name: 'Console-b.js', gzipKB: 19 },
      { name: 'marketing-d.js', gzipKB: 21 }
    ])
    const v = r.violations.find(x => x.name.startsWith('(path: console'))
    expect(v).toBeTruthy()
    expect(v.name).toContain('via marketing')
    expect(v.gzipKB).toBe(139)
    expect(v.overBy).toBe(139 - PATHS.console.budget)
  })

  // Spec 60 — adding a whole console section legitimately grows the total
  // while barely moving what any single reader downloads. The rule this pins:
  // the total may be raised for new surface area; a path budget may not.
  it('a new section costs the total, not the reader', () => {
    const before = [
      { name: 'index-a.js', gzipKB: 83 },
      { name: 'Console-b.js', gzipKB: 6 },
      { name: 'marketing-h.js', gzipKB: 21 },
      { name: 'trust-h.js', gzipKB: 17 }
    ]
    const after = [...before, { name: 'markets-h.js', gzipKB: 9 }]
    const totalOf = cs => cs.reduce((s, c) => s + c.gzipKB, 0)
    expect(totalOf(after)).toBeGreaterThan(totalOf(before))
    // The new section is not the heaviest, so the delivered path is unchanged.
    expect(pathCost(after, PATHS.console).kb).toBe(pathCost(before, PATHS.console).kb)
    expect(evaluateBudget(after).violations.filter(v => v.name.startsWith('(path'))).toEqual([])
  })

  it('a split that raises the total but cuts delivered bytes is not a regression', () => {
    const monolith = [{ name: 'index-a.js', gzipKB: 82 }, { name: 'Console-b.js', gzipKB: 109 }]
    const split = [
      { name: 'index-a.js', gzipKB: 83 },
      { name: 'Console-b.js', gzipKB: 6 },
      ...SECTION_KEYS.map((k, i) => ({ name: `${k}-h.js`, gzipKB: 12 + i }))
    ]
    const totalBefore = monolith.reduce((s, c) => s + c.gzipKB, 0)
    const totalAfter = split.reduce((s, c) => s + c.gzipKB, 0)
    expect(totalAfter).toBeGreaterThan(totalBefore) // the sum got worse...

    // ...while what a reader downloads to open the console got much better.
    const before = 82 + 109
    const after = pathCost(split, PATHS.console).kb
    expect(after).toBeLessThan(before)
    expect(evaluateBudget(split).violations.filter(v => v.name.startsWith('(path'))).toEqual([])
  })
})
