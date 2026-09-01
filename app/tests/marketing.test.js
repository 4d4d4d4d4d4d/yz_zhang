import { describe, it, expect } from 'vitest'
import { allocateBudget, pacingStatus } from '../src/logic/marketing.js'

const sum = obj => Object.values(obj).reduce((s, v) => s + v, 0)

describe('allocateBudget', () => {
  it('conserves the total exactly, even on awkward amounts', () => {
    const { allocations } = allocateBudget(1000.01, [
      { id: 'meta', roas: 3.1 }, { id: 'tiktok', roas: 4.7 }, { id: 'yt', roas: 2.2 }
    ])
    expect(sum(allocations)).toBeCloseTo(1000.01, 10)
  })

  it('respects min and max bounds', () => {
    const { allocations } = allocateBudget(1000, [
      { id: 'a', roas: 10, max: 200 },
      { id: 'b', roas: 1, min: 100 },
      { id: 'c', roas: 1 }
    ])
    expect(allocations.a).toBe(200)
    expect(allocations.b).toBeGreaterThanOrEqual(100)
    expect(sum(allocations)).toBeCloseTo(1000, 10)
  })

  it('water-fills: residue from a capped channel flows to the rest', () => {
    const { allocations } = allocateBudget(1000, [
      { id: 'hot', roas: 9, max: 100 },
      { id: 'warm', roas: 1 }
    ])
    expect(allocations.hot).toBe(100)
    expect(allocations.warm).toBe(900)
  })

  it('throws when minimums exceed the total', () => {
    expect(() => allocateBudget(100, [{ id: 'a', roas: 1, min: 80 }, { id: 'b', roas: 1, min: 40 }]))
      .toThrow(/minimums/)
  })

  it('raising ROAS never lowers a channel allocation (monotonic)', () => {
    const base = allocateBudget(1000, [{ id: 'a', roas: 2 }, { id: 'b', roas: 2 }])
    const boosted = allocateBudget(1000, [{ id: 'a', roas: 3 }, { id: 'b', roas: 2 }])
    expect(boosted.allocations.a).toBeGreaterThanOrEqual(base.allocations.a)
  })

  it('reports unallocated budget when every channel is capped', () => {
    const { allocations, unallocated } = allocateBudget(1000, [
      { id: 'a', roas: 2, max: 300 }, { id: 'b', roas: 2, max: 300 }
    ])
    expect(allocations.a).toBe(300)
    expect(allocations.b).toBe(300)
    expect(unallocated).toBe(400)
  })
})

describe('pacingStatus', () => {
  it('classifies under / on-track / over around the ±10% band', () => {
    // budget 1000, 10 days → day 5 target 500, band ±100
    expect(pacingStatus(1000, 380, 5, 10).status).toBe('under')
    expect(pacingStatus(1000, 500, 5, 10).status).toBe('on-track')
    expect(pacingStatus(1000, 601, 5, 10).status).toBe('over')
  })

  it('is safe on day zero', () => {
    const p = pacingStatus(1000, 0, 0, 10)
    expect(p.status).toBe('on-track')
    expect(p.dailyRunRate).toBe(0)
  })

  it('projects total from run rate', () => {
    const p = pacingStatus(1000, 600, 5, 10)
    expect(p.projectedTotal).toBeCloseTo(1200, 10)
  })
})
