import { describe, it, expect } from 'vitest'
import { resolveMotion, nextMotionPref, MOTION_PREFS } from '../src/logic/motion.js'

describe('resolveMotion', () => {
  it('follows the OS under "system"', () => {
    expect(resolveMotion(true, 'system')).toBe(true)
    expect(resolveMotion(false, 'system')).toBe(false)
  })
  it('forces reduce regardless of OS', () => {
    expect(resolveMotion(false, 'reduce')).toBe(true)
  })
  it('forces full regardless of OS', () => {
    expect(resolveMotion(true, 'full')).toBe(false)
  })
  it('defaults to system when pref is omitted or unknown', () => {
    expect(resolveMotion(true)).toBe(true)
    expect(resolveMotion(true, 'nonsense')).toBe(true)
  })
  it('coerces a truthy/falsy OS signal to boolean', () => {
    expect(resolveMotion(undefined, 'system')).toBe(false)
  })
})

describe('nextMotionPref', () => {
  it('cycles system → reduce → full → system', () => {
    expect(nextMotionPref('system')).toBe('reduce')
    expect(nextMotionPref('reduce')).toBe('full')
    expect(nextMotionPref('full')).toBe('system')
  })
  it('recovers from an unknown value', () => {
    expect(nextMotionPref('xyz')).toBe('system')
  })
  it('exposes the three prefs', () => {
    expect(MOTION_PREFS).toEqual(['system', 'reduce', 'full'])
  })
})
