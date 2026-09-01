import { describe, it, expect } from 'vitest'
import { pushRecent } from '../src/logic/recents.js'

describe('pushRecent — MRU list', () => {
  it('adds a new item to the front', () => {
    expect(pushRecent(['a', 'b'], 'c')).toEqual(['c', 'a', 'b'])
  })

  it('moves an existing item to the front (de-dup)', () => {
    expect(pushRecent(['a', 'b', 'c'], 'c')).toEqual(['c', 'a', 'b'])
  })

  it('caps the list at max, dropping the oldest', () => {
    expect(pushRecent(['a', 'b', 'c'], 'd', 3)).toEqual(['d', 'a', 'b'])
  })

  it('does not mutate the input array', () => {
    const input = ['a', 'b']
    pushRecent(input, 'c')
    expect(input).toEqual(['a', 'b'])
  })

  it('ignores empty or whitespace items', () => {
    expect(pushRecent(['a'], '')).toEqual(['a'])
    expect(pushRecent(['a'], '   ')).toEqual(['a'])
    expect(pushRecent(['a'], null)).toEqual(['a'])
  })

  it('handles a missing/invalid list', () => {
    expect(pushRecent(undefined, 'a')).toEqual(['a'])
    expect(pushRecent(null, '')).toEqual([])
  })

  it('trims the item before comparing', () => {
    expect(pushRecent(['a'], ' a ')).toEqual(['a'])
  })
})
