import { describe, it, expect } from 'vitest'
import { resolveGoto, GOTO_MAP } from '../src/logic/shortcuts.js'
import { SECTIONS } from '../src/console/registry.js'

describe('g-goto shortcut map', () => {
  it('keys are unique — no double-booked letter', () => {
    const keys = Object.keys(GOTO_MAP)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('covers every console section plus home', () => {
    const mapped = Object.values(GOTO_MAP)
      .filter(r => r.name === 'console')
      .map(r => r.params.tab)
      .sort()
    expect(mapped).toEqual(SECTIONS.map(s => s.key).sort())
    expect(Object.values(GOTO_MAP).some(r => r.name === 'home')).toBe(true)
  })

  it('resolveGoto maps each key and is case-insensitive', () => {
    expect(resolveGoto('t')).toEqual({ name: 'console', params: { tab: 'trust' } })
    expect(resolveGoto('T')).toEqual({ name: 'console', params: { tab: 'trust' } })
    expect(resolveGoto('h')).toEqual({ name: 'home' })
  })

  it('returns null for unknown or empty keys', () => {
    expect(resolveGoto('z')).toBeNull()
    expect(resolveGoto('')).toBeNull()
    expect(resolveGoto(' ')).toBeNull()
    expect(resolveGoto(undefined)).toBeNull()
  })
})
