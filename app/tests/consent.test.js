import { describe, it, expect } from 'vitest'
import { defaultConsent, normalizeConsent, canTrack, decide, OPTIONAL_CATEGORIES } from '../src/logic/consent.js'

describe('defaultConsent', () => {
  it('is privacy-by-default: undecided, analytics off', () => {
    expect(defaultConsent()).toEqual({ analytics: false, decided: false })
  })
})

describe('normalizeConsent', () => {
  it('coerces a valid object', () => {
    expect(normalizeConsent({ analytics: 1, decided: 'yes' })).toEqual({ analytics: true, decided: true })
  })
  it('falls back to default for junk', () => {
    expect(normalizeConsent(null)).toEqual({ analytics: false, decided: false })
    expect(normalizeConsent('nope')).toEqual({ analytics: false, decided: false })
  })
})

describe('canTrack', () => {
  it('always allows necessary', () => {
    expect(canTrack('necessary', defaultConsent())).toBe(true)
    expect(canTrack('necessary', null)).toBe(true)
  })
  it('gates analytics on explicit opt-in', () => {
    expect(canTrack('analytics', { analytics: false })).toBe(false)
    expect(canTrack('analytics', { analytics: true })).toBe(true)
    expect(canTrack('analytics', undefined)).toBe(false)
  })
})

describe('decide', () => {
  it('accept opts into analytics and marks decided', () => {
    expect(decide('accept')).toEqual({ analytics: true, decided: true })
  })
  it('reject opts out but marks decided', () => {
    expect(decide('reject')).toEqual({ analytics: false, decided: true })
  })
  it('accepts a granular object', () => {
    expect(decide({ analytics: true })).toEqual({ analytics: true, decided: true })
    expect(decide({})).toEqual({ analytics: false, decided: true })
  })
})

describe('OPTIONAL_CATEGORIES', () => {
  it('lists analytics as the sole optional category', () => {
    expect(OPTIONAL_CATEGORIES).toEqual(['analytics'])
  })
})
