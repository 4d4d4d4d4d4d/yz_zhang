import { describe, it, expect } from 'vitest'
import { resolveGoto, GOTO_MAP, shortcutRows } from '../src/logic/shortcuts.js'
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

describe('shortcutRows — cheat-sheet generation', () => {
  it('generates one goto row per GOTO_MAP key, each with its route', () => {
    const { goto } = shortcutRows()
    expect(goto).toHaveLength(Object.keys(GOTO_MAP).length)
    for (const row of goto) {
      expect(row.keys[0]).toBe('g')
      expect(GOTO_MAP[row.keys[1]]).toEqual(row.route)
    }
  })

  it('every goto row targets a real destination (home or a live section)', () => {
    const tabs = new Set(SECTIONS.map(s => s.key))
    for (const row of shortcutRows().goto) {
      if (row.route.name === 'home') continue
      expect(tabs.has(row.route.params.tab)).toBe(true)
    }
  })

  it('lists the global shortcuts (palette, help, tabs)', () => {
    const ids = shortcutRows().global.map(r => r.id)
    expect(ids).toEqual(expect.arrayContaining(['palette', 'help', 'tabs']))
  })
})
