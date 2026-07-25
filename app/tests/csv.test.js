import { describe, it, expect } from 'vitest'
import { csvCell, toCsv } from '../src/logic/csv.js'

const COLS = [{ key: 'id', label: 'Order' }, { key: 'total', label: 'Total' }]

describe('csvCell — RFC 4180 quoting', () => {
  it('leaves plain values unquoted', () => {
    expect(csvCell('abc')).toBe('abc')
    expect(csvCell(42)).toBe('42')
  })
  it('quotes when a comma is present', () => {
    expect(csvCell('a,b')).toBe('"a,b"')
  })
  it('quotes and doubles embedded quotes', () => {
    expect(csvCell('a "b" c')).toBe('"a ""b"" c"')
  })
  it('quotes on newlines', () => {
    expect(csvCell('a\nb')).toBe('"a\nb"')
  })
  it('renders nullish as empty', () => {
    expect(csvCell(null)).toBe('')
    expect(csvCell(undefined)).toBe('')
  })
})

describe('toCsv', () => {
  it('emits a header then CRLF-joined rows', () => {
    const csv = toCsv([{ id: 'O-1', total: 100 }, { id: 'O-2', total: 200 }], COLS)
    expect(csv).toBe('Order,Total\r\nO-1,100\r\nO-2,200')
  })
  it('quotes cells that need it', () => {
    const csv = toCsv([{ id: 'Lumen, Inc', total: 5 }], COLS)
    expect(csv).toContain('"Lumen, Inc",5')
  })
  it('returns just the header for no rows', () => {
    expect(toCsv([], COLS)).toBe('Order,Total')
  })
  it('falls back to the key when a column has no label', () => {
    expect(toCsv([], [{ key: 'x' }])).toBe('x')
  })
  it('guards non-array inputs', () => {
    expect(toCsv(null, null)).toBe('')
  })
})
