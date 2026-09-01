import { describe, it, expect } from 'vitest'
import { sortRows, compareVals, nextDir } from '../src/logic/sortRows.js'

const rows = [
  { id: 'b', n: 3, tie: 'x' },
  { id: 'a', n: 1, tie: 'x' },
  { id: 'c', n: 1, tie: 'x' }
]

describe('compareVals', () => {
  it('compares numbers numerically', () => {
    expect(compareVals(2, 10)).toBeLessThan(0)
  })
  it('compares strings lexically', () => {
    expect(compareVals('b', 'a')).toBeGreaterThan(0)
  })
  it('treats nullish as empty string', () => {
    expect(compareVals(undefined, '')).toBe(0)
  })
})

describe('sortRows', () => {
  it('sorts ascending by a string key', () => {
    expect(sortRows(rows, 'id').map(r => r.id)).toEqual(['a', 'b', 'c'])
  })
  it('sorts descending', () => {
    expect(sortRows(rows, 'id', 'desc').map(r => r.id)).toEqual(['c', 'b', 'a'])
  })
  it('sorts numbers numerically, not lexically', () => {
    const r = [{ v: 10 }, { v: 2 }, { v: 1 }]
    expect(sortRows(r, 'v').map(x => x.v)).toEqual([1, 2, 10])
  })
  it('is stable — equal keys keep input order', () => {
    // n=1 for both 'a' (index 1) and 'c' (index 2): 'a' must precede 'c'
    expect(sortRows(rows, 'n').map(r => r.id)).toEqual(['a', 'c', 'b'])
  })
  it('returns a copy (no key) without mutating input', () => {
    const out = sortRows(rows, null)
    expect(out).not.toBe(rows)
    expect(out.map(r => r.id)).toEqual(['b', 'a', 'c'])
  })
  it('does not mutate the source array when sorting', () => {
    const before = rows.map(r => r.id)
    sortRows(rows, 'id', 'desc')
    expect(rows.map(r => r.id)).toEqual(before)
  })
  it('guards a non-array input', () => {
    expect(sortRows(null, 'id')).toEqual([])
  })
  it('supports a custom accessor', () => {
    const r = [{ a: { x: 2 } }, { a: { x: 1 } }]
    expect(sortRows(r, 'x', 'asc', (row, k) => row.a[k]).map(o => o.a.x)).toEqual([1, 2])
  })
})

describe('nextDir', () => {
  it('starts a new column ascending', () => {
    expect(nextDir('id', 'partner', 'desc')).toBe('asc')
  })
  it('toggles the active column asc → desc → asc', () => {
    expect(nextDir('id', 'id', 'asc')).toBe('desc')
    expect(nextDir('id', 'id', 'desc')).toBe('asc')
  })
})
