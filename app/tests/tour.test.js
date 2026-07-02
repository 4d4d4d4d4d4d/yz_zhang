import { describe, it, expect } from 'vitest'
import { validateTour, shortestPath, coverage, pickRendition } from '../src/logic/tour.js'

const TOUR = {
  entrance: 'lobby',
  stations: [
    { id: 'lobby',  name: 'Lobby',   zone: 'front', hotspots: [{ to: 'lineA' }, { to: 'show' }] },
    { id: 'show',   name: 'Showroom', zone: 'front', hotspots: [{ to: 'lobby' }] },
    { id: 'lineA',  name: 'Line A',  zone: 'mfg',   hotspots: [{ to: 'lobby' }, { to: 'qa' }] },
    { id: 'qa',     name: 'QA Lab',  zone: 'qc',    hotspots: [{ to: 'lineA' }, { to: 'clean' }] },
    { id: 'clean',  name: 'Clean Room', zone: 'qc', hotspots: [{ to: 'qa' }] }
  ]
}

describe('validateTour', () => {
  it('accepts a well-formed tour', () => {
    expect(validateTour(TOUR).ok).toBe(true)
  })

  it('catches dangling hotspots, duplicate ids and unreachable stations', () => {
    const bad = {
      entrance: 'a',
      stations: [
        { id: 'a', hotspots: [{ to: 'ghost' }] },
        { id: 'a', hotspots: [] },            // dup
        { id: 'island', hotspots: [] }        // unreachable
      ]
    }
    const kinds = validateTour(bad).problems.map(p => p.kind)
    expect(kinds).toContain('dangling-hotspot')
    expect(kinds).toContain('duplicate-id')
    expect(kinds).toContain('unreachable')
  })

  it('flags a missing entrance', () => {
    const r = validateTour({ stations: [{ id: 'x', hotspots: [] }] })
    expect(r.problems.map(p => p.kind)).toContain('missing-entrance')
  })
})

describe('shortestPath', () => {
  it('finds the hop-minimal walkway path', () => {
    expect(shortestPath(TOUR, 'show', 'clean')).toEqual(['show', 'lobby', 'lineA', 'qa', 'clean'])
  })

  it('same station → single-node path; unknown or unreachable → null', () => {
    expect(shortestPath(TOUR, 'qa', 'qa')).toEqual(['qa'])
    expect(shortestPath(TOUR, 'qa', 'nowhere')).toBeNull()
    const oneWay = { stations: [{ id: 'a', hotspots: [] }, { id: 'b', hotspots: [{ to: 'a' }] }] }
    expect(shortestPath(oneWay, 'a', 'b')).toBeNull()
  })
})

describe('coverage', () => {
  it('computes percent, per-zone breakdown and the missed list', () => {
    const c = coverage(['lobby', 'lineA'], TOUR)
    expect(c.percent).toBe(40)
    expect(c.zones.front).toEqual({ total: 2, visited: 1 })
    expect(c.zones.qc).toEqual({ total: 2, visited: 0 })
    expect(c.missed.map(m => m.id)).toEqual(['show', 'qa', 'clean'])
  })

  it('empty tour is 0% and empty visit list misses everything', () => {
    expect(coverage([], {}).percent).toBe(0)
    expect(coverage([], TOUR).missed).toHaveLength(5)
  })
})

describe('pickRendition', () => {
  const R = [
    { id: '8k', minMbps: 50 }, { id: '4k', minMbps: 25 },
    { id: '1080p', minMbps: 8 }, { id: '720p', minMbps: 3 }
  ]

  it('picks the best rendition the link can carry, exact at thresholds', () => {
    expect(pickRendition(60, R).id).toBe('8k')
    expect(pickRendition(50, R).id).toBe('8k')
    expect(pickRendition(49.9, R).id).toBe('4k')
    expect(pickRendition(8, R).id).toBe('1080p')
  })

  it('floors at the lowest rendition — degrade, never deny', () => {
    expect(pickRendition(0, R).id).toBe('720p')
  })

  it('is monotonic in bandwidth', () => {
    let last = -1
    for (const bw of [0, 2, 5, 10, 30, 55]) {
      const idx = R.findIndex(r => r.id === pickRendition(bw, R).id)
      const quality = R.length - idx
      expect(quality).toBeGreaterThanOrEqual(last)
      last = quality
    }
  })

  it('empty renditions → null', () => {
    expect(pickRendition(10, [])).toBeNull()
  })
})
