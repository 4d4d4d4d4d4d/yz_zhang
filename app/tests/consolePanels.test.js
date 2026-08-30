import { describe, it, expect } from 'vitest'
import { SECTIONS } from '../src/console/registry.js'
import { loadSection, prefetchSection, isSectionLoaded, loadableSections } from '../src/console/panels.js'
import { prefetchOrder, idleSchedule, requestIdle } from '../src/logic/prefetch.js'

describe('console section chunks (spec 59)', () => {
  it('offers a loader for exactly the sections in the registry', () => {
    expect([...loadableSections].sort()).toEqual(SECTIONS.map(s => s.key).sort())
  })

  it('every registry sub-tab resolves to a real component', async () => {
    for (const section of SECTIONS) {
      const panels = await loadSection(section.key)
      for (const sub of section.subs) {
        expect(panels[sub], `${section.key}/${sub} has no component`).toBeTruthy()
      }
      // And nothing ships that the console cannot reach — a panel with no
      // sub-tab is dead weight in the chunk, which is the orphan problem
      // spec 55 guards for logic modules.
      const extra = Object.keys(panels).filter(k => !section.subs.includes(k))
      expect(extra, `${section.key} ships unreachable panels`).toEqual([])
    }
  })

  it('caches: a second load is the same promise, not a second import', async () => {
    const a = loadSection('deals')
    const b = loadSection('deals')
    expect(a).toBe(b)
    expect(await a).toBe(await b)
    expect(isSectionLoaded('deals')).toBe(true)
  })

  it('rejects an unknown section instead of resolving to undefined', async () => {
    await expect(loadSection('nope')).rejects.toThrow(/Unknown console section/)
    expect(isSectionLoaded('nope')).toBe(false)
  })

  it('prefetch is failure-tolerant — speculation must never throw', async () => {
    await expect(prefetchSection('nope')).resolves.toBe(false)
    await expect(prefetchSection('trust')).resolves.toBe(true)
  })
})

describe('prefetch policy (spec 59)', () => {
  const KEYS = SECTIONS.map(s => s.key)

  it('never warms the section already being loaded', () => {
    expect(prefetchOrder(KEYS, 'deals', ['deals', 'deals'])).not.toContain('deals')
  })

  it('prefers where the reader has actually been, most recent first', () => {
    expect(prefetchOrder(KEYS, 'recommend', ['trust', 'deals', 'marketing'])).toEqual(['trust', 'deals'])
  })

  it('falls back to the sidebar neighbours when there is no history', () => {
    // recommend is first in the sidebar, so only the one below it exists.
    expect(prefetchOrder(KEYS, 'recommend', [])).toEqual(['marketing'])
    expect(prefetchOrder(KEYS, 'deals', [])).toEqual(['showcase', 'partners'])
    expect(prefetchOrder(KEYS, 'trust', [])).toEqual(['immersive'])
  })

  it('is capped — prefetching everything defeats the split', () => {
    expect(prefetchOrder(KEYS, 'deals', KEYS)).toHaveLength(2)
    expect(prefetchOrder(KEYS, 'deals', KEYS, { max: 4 })).toHaveLength(4)
    expect(prefetchOrder(KEYS, 'deals', [], { max: 0 })).toEqual([])
  })

  it('ignores history entries that are not real sections', () => {
    expect(prefetchOrder(KEYS, 'deals', ['ghost', '', null, 'trust'])).toEqual(['trust', 'showcase'])
  })

  it('never repeats a section', () => {
    const out = prefetchOrder(KEYS, 'deals', ['showcase', 'showcase', 'partners'])
    expect(new Set(out).size).toBe(out.length)
  })

  it('degrades safely when the active key is unknown or the list is empty', () => {
    expect(prefetchOrder([], 'deals', ['trust'])).toEqual([])
    expect(prefetchOrder(KEYS, 'ghost', [])).toEqual([])
    expect(prefetchOrder(KEYS, 'ghost', ['trust'])).toEqual(['trust'])
  })
})

describe('idle scheduling (spec 59)', () => {
  it('uses requestIdleCallback when the runtime has one', () => {
    const calls = []
    const schedule = idleSchedule({ requestIdleCallback: (cb, opts) => { calls.push(opts); cb() } })
    let ran = false
    requestIdle(() => { ran = true }, schedule)
    expect(ran).toBe(true)
    expect(calls[0]).toEqual({ timeout: 2000 })
  })

  it('falls back to a timer, then to running inline', () => {
    let delay = null
    const timer = idleSchedule({ setTimeout: (cb, ms) => { delay = ms; cb() } })
    let ran = false
    requestIdle(() => { ran = true }, timer)
    expect(ran).toBe(true)
    expect(delay).toBe(200)

    let inlineRan = false
    requestIdle(() => { inlineRan = true }, idleSchedule({}))
    expect(inlineRan).toBe(true)
  })

  it('swallows a throwing callback — speculative work must not surface', () => {
    expect(() => requestIdle(() => { throw new Error('boom') }, idleSchedule({}))).not.toThrow()
  })
})
