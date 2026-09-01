import { describe, it, expect } from 'vitest'
import { analyzeFunnel } from '../src/logic/funnel.js'

const STAGES = ['page_view', 'form_view', 'form_submit', 'form_success']

function stream(counts) {
  const events = []
  for (const [name, n] of Object.entries(counts)) {
    for (let i = 0; i < n; i++) events.push({ name })
  }
  return events
}

describe('analyzeFunnel', () => {
  it('computes per-step retention, overall conversion, and the biggest drop', () => {
    const events = stream({ page_view: 1000, form_view: 400, form_submit: 120, form_success: 90 })
    const { steps, overall, biggestDrop } = analyzeFunnel(events, STAGES)
    expect(steps.map(s => s.count)).toEqual([1000, 400, 120, 90])
    expect(steps[0].rate).toBe(1)
    expect(steps[1].rate).toBeCloseTo(0.4, 6)   // 400/1000
    expect(steps[2].rate).toBeCloseTo(0.3, 6)   // 120/400
    expect(steps[3].rate).toBeCloseTo(0.75, 6)  // 90/120
    expect(overall).toBeCloseTo(0.09, 6)        // 90/1000
    expect(biggestDrop.stage).toBe('form_submit') // 0.30 is the worst retention
    expect(biggestDrop.from).toBe('form_view')
  })

  it('is div-by-zero safe: a zero upstream yields rate 0, not NaN', () => {
    const { steps } = analyzeFunnel(stream({ form_submit: 5 }), STAGES)
    expect(steps[1].rate).toBe(0) // form_view count 0 upstream
    expect(steps.every(s => Number.isFinite(s.rate))).toBe(true)
  })

  it('ignores events that are not funnel stages', () => {
    const events = [...stream({ page_view: 10, form_view: 5 }), { name: 'cta_click' }, { name: 'noise' }]
    const { steps } = analyzeFunnel(events, STAGES)
    expect(steps[0].count).toBe(10)
    expect(steps[1].count).toBe(5)
  })

  it('empty stream → all-zero steps, overall 0, biggestDrop present but zero-rate', () => {
    const { steps, overall, biggestDrop } = analyzeFunnel([], STAGES)
    expect(steps.map(s => s.count)).toEqual([0, 0, 0, 0])
    expect(overall).toBe(0)
    expect(biggestDrop.rate).toBe(0)
  })

  it('a single-stage funnel has no drop to report', () => {
    expect(analyzeFunnel(stream({ page_view: 3 }), ['page_view']).biggestDrop).toBeNull()
  })

  it('reports rate > 1 as-is when a later stage exceeds its predecessor (re-submits)', () => {
    const { steps } = analyzeFunnel(stream({ form_view: 10, form_submit: 14 }), ['form_view', 'form_submit'])
    expect(steps[1].rate).toBeCloseTo(1.4, 6)
  })
})
