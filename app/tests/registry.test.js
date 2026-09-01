import { describe, it, expect } from 'vitest'
import { SECTIONS } from '../src/console/registry.js'

// Spec 20 — structural invariants on the single-source console registry.
describe('console registry', () => {
  it('section keys are unique', () => {
    const keys = SECTIONS.map(s => s.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('every section has an icon and at least one sub-tab', () => {
    for (const s of SECTIONS) {
      expect(s.icon, `${s.key} icon`).toBeTruthy()
      expect(Array.isArray(s.subs) && s.subs.length > 0, `${s.key} subs`).toBe(true)
    }
  })

  it('sub-tab keys are unique within each section', () => {
    for (const s of SECTIONS) {
      expect(new Set(s.subs).size, `${s.key} has duplicate subs`).toBe(s.subs.length)
    }
  })

  it('all keys are lowercase slugs (usable in i18n paths and routes)', () => {
    for (const s of SECTIONS) {
      expect(s.key).toMatch(/^[a-z]+$/)
      for (const v of s.subs) expect(v, `${s.key}/${v}`).toMatch(/^[a-z]+$/)
    }
  })
})
