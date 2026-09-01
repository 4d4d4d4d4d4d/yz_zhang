import { describe, it, expect } from 'vitest'
import {
  stageWeight, weightedPipeline, categoryTotals, closedWonTotal, openPipeline,
  coverageRatio, auditCategories, forecastSummary, DEFAULT_STAGES, COVERAGE_BENCHMARK
} from '../src/logic/salesForecast.js'

// The shipped board dataset. D-2842 is Closed Won AND category 'commit' —
// the overlap that the previous inline implementation double-counted.
const DEALS = [
  { id: 'D-2841', stage: 'Negotiation', value: 840000, category: 'best' },
  { id: 'D-2842', stage: 'Closed Won', value: 1200000, category: 'commit' },
  { id: 'D-2843', stage: 'Verbal', value: 620000, category: 'commit' },
  { id: 'D-2844', stage: 'Proposal', value: 980000, category: 'best' },
  { id: 'D-2845', stage: 'Negotiation', value: 220000, category: 'commit' },
  { id: 'D-2846', stage: 'Discovery', value: 540000, category: 'upside' },
  { id: 'D-2847', stage: 'Lead', value: 140000, category: 'upside' },
  { id: 'D-2848', stage: 'Proposal', value: 380000, category: 'best' },
  { id: 'D-2849', stage: 'Discovery', value: 95000, category: 'upside' }
]
const QUOTA = 4200000

describe('stage weights', () => {
  it('reads the ladder weight by name', () => {
    expect(stageWeight('Closed Won')).toBe(1)
    expect(stageWeight('Lead')).toBe(0.1)
  })
  it('is 0 for an unknown stage rather than NaN', () => {
    expect(stageWeight('Atlantis')).toBe(0)
  })
  it('is ordered low → high along the funnel', () => {
    const w = DEFAULT_STAGES.map(s => s.weight)
    expect(w).toEqual([...w].sort((a, b) => a - b))
  })
})

describe('weightedPipeline', () => {
  it('weights each deal by its stage probability', () => {
    const w = weightedPipeline([
      { stage: 'Closed Won', value: 100 },
      { stage: 'Lead', value: 100 }
    ])
    expect(w).toBeCloseTo(110, 6)
  })
  it('guards bad input', () => {
    expect(weightedPipeline(null)).toBe(0)
    expect(weightedPipeline([{ stage: 'Lead', value: 'x' }])).toBe(0)
  })
})

describe('category totals', () => {
  it('partitions by category and ignores unknown ones', () => {
    const t = categoryTotals([...DEALS, { id: 'X', stage: 'Lead', value: 999, category: 'bogus' }])
    expect(t.commit).toBe(2040000)
    expect(t.best).toBe(2200000)
    expect(t.upside).toBe(775000)
  })
})

describe('REGRESSION — attainment must not double-count Closed Won', () => {
  it('counts a Closed Won deal once, through its commit category', () => {
    const s = forecastSummary({ deals: DEALS, quota: QUOTA })
    // Closed Won ($1.2M) is inside commit ($2.04M) — committed is NOT their sum.
    expect(s.closedWon).toBe(1200000)
    expect(s.commit).toBe(2040000)
    expect(s.committed).toBe(2040000)
    expect(s.committed).not.toBe(s.closedWon + s.commit) // the old bug
    expect(Math.round(s.attainment)).toBe(49) // was reported as 77
  })

  it('reports the true gap, not one shrunk by the double count', () => {
    const s = forecastSummary({ deals: DEALS, quota: QUOTA })
    expect(s.gap).toBe(2160000) // was reported as 960000
  })
})

describe('forecast roll-up', () => {
  const s = forecastSummary({ deals: DEALS, quota: QUOTA })

  it('nests commit ⊆ bestCase ⊆ allIn', () => {
    expect(s.bestCase).toBe(s.committed + s.best)
    expect(s.allIn).toBe(s.bestCase + s.upside)
    expect(s.committed).toBeLessThanOrEqual(s.bestCase)
    expect(s.bestCase).toBeLessThanOrEqual(s.allIn)
  })

  it('excludes Closed Won from open pipeline', () => {
    expect(s.openPipeline).toBe(openPipeline(DEALS))
    expect(s.openPipeline).toBe(3815000)
    expect(closedWonTotal(DEALS)).toBe(1200000)
  })

  it('computes coverage against the remaining gap', () => {
    expect(s.coverage).toBeCloseTo(3815000 / 2160000, 6)
    expect(s.coverage).toBeGreaterThan(1)
    expect(s.coverageHealthy).toBe(s.coverage >= COVERAGE_BENCHMARK)
  })
})

describe('coverageRatio', () => {
  it('is pipeline ÷ gap', () => {
    expect(coverageRatio(300, 100)).toBe(3)
  })
  it('is null once the gap is closed', () => {
    expect(coverageRatio(300, 0)).toBeNull()
    expect(coverageRatio(300, -50)).toBeNull()
  })
})

describe('auditCategories', () => {
  it('flags a Closed Won deal that is not in commit', () => {
    const issues = auditCategories([{ id: 'BAD', stage: 'Closed Won', value: 10, category: 'best' }])
    expect(issues).toEqual([{ id: 'BAD', issue: 'closed-won-not-commit' }])
  })
  it('is clean for the shipped dataset', () => {
    expect(auditCategories(DEALS)).toEqual([])
  })
})

describe('guards', () => {
  it('handles an empty forecast', () => {
    const s = forecastSummary()
    expect(s.attainment).toBe(0)
    expect(s.committed).toBe(0)
    expect(s.coverage).toBeNull()
  })
  it('treats a met quota as covered', () => {
    const s = forecastSummary({ deals: [{ stage: 'Closed Won', value: 500, category: 'commit' }], quota: 100 })
    expect(s.gap).toBe(0)
    expect(s.coverage).toBeNull()
    expect(s.coverageHealthy).toBe(true)
  })
})
