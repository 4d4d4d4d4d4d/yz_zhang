import { describe, it, expect } from 'vitest'
import { buildRenderPlan, advanceProgress } from '../src/logic/render.js'

const CATALOG = {
  markets: [
    { id: 'US', label: 'United States', lang: 'en-US' },
    { id: 'JP', label: 'Japan', lang: 'ja-JP' }
  ],
  formats: [
    { id: '9x16', label: '9:16 · short video' },
    { id: '1x1', label: '1:1 · feed' }
  ]
}

describe('buildRenderPlan', () => {
  it('expands the full market × format cartesian product', () => {
    const plan = buildRenderPlan({ targets: ['US', 'JP'], formats: ['9x16', '1x1'] }, CATALOG)
    expect(plan.planned).toBe(4)
    expect(plan.items.map(i => i.id)).toEqual(['US-9x16', 'US-1x1', 'JP-9x16', 'JP-1x1'])
    expect(plan.items[2]).toMatchObject({ market: 'Japan', lang: 'ja-JP', format: '9:16 · short video', progress: 0 })
    expect(plan.skipped).toEqual([])
  })

  it('reports unknown ids in skipped[] instead of silently dropping them', () => {
    const plan = buildRenderPlan({ targets: ['US', 'MARS'], formats: ['9x16', 'holo'] }, CATALOG)
    expect(plan.planned).toBe(1)
    expect(plan.skipped).toEqual([
      { kind: 'format', id: 'holo' },
      { kind: 'market', id: 'MARS' }
    ])
  })

  it('empty selections → empty plan, no throw', () => {
    expect(buildRenderPlan({}, CATALOG).planned).toBe(0)
    expect(buildRenderPlan().items).toEqual([])
  })
})

describe('advanceProgress', () => {
  it('advances between +8 and +22 per tick under an injected RNG', () => {
    expect(advanceProgress(0, () => 0)).toBe(8)
    expect(advanceProgress(0, () => 1)).toBe(22)
    expect(advanceProgress(50, () => 0.5)).toBe(65)
  })

  it('caps at 100 and is deterministic per rng', () => {
    expect(advanceProgress(95, () => 1)).toBe(100)
    const rngA = () => 0.25, rngB = () => 0.25
    expect(advanceProgress(40, rngA)).toBe(advanceProgress(40, rngB))
  })

  it('always reaches 100 in bounded ticks', () => {
    let p = 0, ticks = 0
    while (p < 100 && ticks < 20) { p = advanceProgress(p, () => 0); ticks++ }
    expect(p).toBe(100)
    expect(ticks).toBeLessThanOrEqual(13) // 100/8 = 12.5
  })
})
