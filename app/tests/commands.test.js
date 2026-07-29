import { describe, it, expect } from 'vitest'
import { buildActionCommands } from '../src/logic/commands.js'

describe('buildActionCommands', () => {
  it('emits one locale action per locale and one motion action per pref', () => {
    const acts = buildActionCommands({ locales: ['en', 'zh'], motionPrefs: ['system', 'reduce'] })
    expect(acts).toHaveLength(4)
    expect(acts.filter(a => a.kind === 'locale').map(a => a.arg)).toEqual(['en', 'zh'])
    expect(acts.filter(a => a.kind === 'motion').map(a => a.arg)).toEqual(['system', 'reduce'])
  })

  it('ids are unique and namespaced under act:', () => {
    const ids = buildActionCommands({ locales: ['en', 'zh', 'ja', 'es'], motionPrefs: ['system', 'reduce', 'full'] }).map(a => a.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.every(id => id.startsWith('act:'))).toBe(true)
  })

  it('defaults to an empty list', () => {
    expect(buildActionCommands()).toEqual([])
    expect(buildActionCommands({})).toEqual([])
    expect(buildActionCommands({ locales: ['en'] })).toHaveLength(1)
  })
})
