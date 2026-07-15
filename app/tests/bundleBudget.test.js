import { describe, it, expect } from 'vitest'
import { evaluateBudget, budgetFor, BUDGETS, TOTAL_BUDGET } from '../src/logic/bundleBudget.js'

describe('budgetFor', () => {
  it('matches by filename prefix, falls back to DEFAULT', () => {
    expect(budgetFor('Console-abc123.js')).toBe(BUDGETS.Console)
    expect(budgetFor('index-xyz.js')).toBe(BUDGETS.index)
    expect(budgetFor('Studio-foo.js')).toBe(BUDGETS.DEFAULT)
  })
})

describe('evaluateBudget', () => {
  it('passes when every chunk and the total are within budget', () => {
    const r = evaluateBudget([
      { name: 'Console-a.js', gzipKB: 90 },
      { name: 'index-b.js', gzipKB: 81 },
      { name: 'Studio-c.js', gzipKB: 5 }
    ])
    expect(r.ok).toBe(true)
    expect(r.violations).toEqual([])
    expect(r.totalKB).toBe(176)
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
