import { describe, it, expect } from 'vitest'
import { readiness, readinessRank, GATE_KINDS } from '../src/logic/goLive.js'
import { backwardPlan, upcomingMoments, atRisk, leadTimeDays, STAGES } from '../src/logic/retailMoments.js'

const DAY = 86400000
const NOW = Date.UTC(2026, 0, 15) // fixed clock — no ambient time in assertions

const gate = (key, kind, status, etaDays = 0, weight = 1, owner = 'ops') =>
  ({ key, kind, status, etaDays, weight, owner })

describe('goLive · blocking gates withhold, they do not average', () => {
  it('an unmet blocking gate stops go-live no matter how polished everything else is', () => {
    const r = readiness([
      gate('vat', GATE_KINDS.blocking, 'open', 30),
      ...Array.from({ length: 9 }, (_, i) => gate(`a${i}`, GATE_KINDS.advisory, 'done'))
    ], NOW)
    expect(r.canGoLive).toBe(false)
    expect(r.blockers).toEqual(['vat'])
    // The comfortable number is still reported — but it cannot mask the block.
    expect(r.advisoryPct).toBe(100)
    expect(r.blockingPct).toBe(0)
  })

  it('all blocking gates met means the market can transact', () => {
    const r = readiness([
      gate('vat', GATE_KINDS.blocking, 'done'),
      gate('entity', GATE_KINDS.blocking, 'done'),
      gate('helpdesk', GATE_KINDS.advisory, 'open', 5)
    ], NOW)
    expect(r.canGoLive).toBe(true)
    expect(r.blockers).toEqual([])
    expect(r.blockingPct).toBe(100)
    expect(r.advisoryPct).toBe(0)
  })

  it('advisory gates are weighted — not every checklist row is equal', () => {
    const r = readiness([
      gate('big', GATE_KINDS.advisory, 'done', 0, 9),
      gate('small', GATE_KINDS.advisory, 'open', 0, 1)
    ], NOW)
    expect(r.advisoryPct).toBe(90)
  })

  it('critical path is the longest pole, not the sum — remediation runs in parallel', () => {
    const r = readiness([
      gate('a', GATE_KINDS.advisory, 'open', 10, 1, 'legal'),
      gate('b', GATE_KINDS.advisory, 'open', 25, 1, 'finance'),
      gate('c', GATE_KINDS.advisory, 'open', 7, 1, 'ops')
    ], NOW)
    expect(r.criticalPathDays).toBe(25) // not 42
    expect(r.earliestGoLive).toBe(NOW + 25 * DAY)
    expect(r.owner).toBe('finance') // who to chase
  })

  it('a fully done market is live today', () => {
    const r = readiness([gate('vat', GATE_KINDS.blocking, 'done')], NOW)
    expect(r.criticalPathDays).toBe(0)
    expect(r.earliestGoLive).toBe(NOW)
    expect(r.openCount).toBe(0)
    expect(r.owner).toBeNull()
  })

  it('no gates at all is vacuously ready, and says so with 100/100', () => {
    const r = readiness([], NOW)
    expect(r).toMatchObject({ canGoLive: true, advisoryPct: 100, blockingPct: 100, openCount: 0 })
    expect(readiness(undefined, NOW).canGoLive).toBe(true)
    expect(readiness(null, NOW).blockers).toEqual([])
  })

  it('junk weights and etas degrade to zero rather than NaN', () => {
    const r = readiness([
      { key: 'x', kind: 'advisory', status: 'open', weight: 'abc', etaDays: null },
      { key: 'y', kind: 'advisory', status: 'done', weight: -4 }
    ], NOW)
    expect(Number.isFinite(r.advisoryPct)).toBe(true)
    expect(r.criticalPathDays).toBe(0)
  })
})

describe('goLive · ranking', () => {
  it('a market that cannot transact ranks below every one that can', () => {
    const ranked = readinessRank([
      { code: 'POLISHED', gates: [gate('vat', GATE_KINDS.blocking, 'open', 2), gate('a', 'advisory', 'done')] },
      { code: 'ROUGH', gates: [gate('vat', GATE_KINDS.blocking, 'done'), gate('a', 'advisory', 'open', 40)] }
    ], NOW)
    expect(ranked.map(r => r.code)).toEqual(['ROUGH', 'POLISHED'])
  })

  it('among live-able markets, the shortest critical path wins', () => {
    const ranked = readinessRank([
      { code: 'SLOW', gates: [gate('a', 'advisory', 'open', 30)] },
      { code: 'FAST', gates: [gate('a', 'advisory', 'open', 3)] }
    ], NOW)
    expect(ranked[0].code).toBe('FAST')
  })

  it('empty input ranks empty', () => {
    expect(readinessRank([], NOW)).toEqual([])
    expect(readinessRank(undefined, NOW)).toEqual([])
  })
})

describe('retailMoments · backward planning from an immovable date', () => {
  const LEAD = leadTimeDays() // 25 days across the default pipeline

  it('the plan walks backward and the stages chain end-to-end', () => {
    const at = NOW + 60 * DAY
    const plan = backwardPlan(at, NOW)
    expect(plan.leadDays).toBe(LEAD)
    expect(plan.stages.at(-1).end).toBe(at)
    expect(plan.startBy).toBe(at - LEAD * DAY)
    for (let i = 1; i < plan.stages.length; i++) {
      expect(plan.stages[i].start).toBe(plan.stages[i - 1].end)
    }
    expect(plan.stages.map(s => s.key)).toEqual(STAGES.map(s => s.key))
  })

  it('says a campaign is late TODAY when its start date has already passed', () => {
    const tight = backwardPlan(NOW + 10 * DAY, NOW) // needs 25 days, has 10
    expect(tight.status).toBe('late')
    expect(tight.slackDays).toBe(-15)
    expect(tight.stages[0].late).toBe(true)

    const comfortable = backwardPlan(NOW + 90 * DAY, NOW)
    expect(comfortable.status).toBe('ontrack')
    expect(comfortable.slackDays).toBe(90 - LEAD)
    expect(comfortable.stages.every(s => !s.late)).toBe(true)
  })

  it('distinguishes late-but-reachable from the date having passed', () => {
    expect(backwardPlan(NOW - DAY, NOW).status).toBe('passed')
    expect(backwardPlan(NOW + 5 * DAY, NOW).status).toBe('late')
  })

  it('an empty pipeline means start on the day — no phantom lead time', () => {
    const plan = backwardPlan(NOW + 10 * DAY, NOW, [])
    expect(plan.leadDays).toBe(0)
    expect(plan.startBy).toBe(NOW + 10 * DAY)
    expect(plan.stages).toEqual([])
  })
})

describe('retailMoments · the planning window', () => {
  const MOMENTS = [
    { key: 'past', at: NOW - 10 * DAY },
    { key: 'soon', at: NOW + 12 * DAY },
    { key: 'mid', at: NOW + 100 * DAY },
    { key: 'far', at: NOW + 400 * DAY }
  ]

  it('shows what is ahead and inside the horizon, soonest first', () => {
    expect(upcomingMoments(MOMENTS, NOW).map(m => m.key)).toEqual(['soon', 'mid'])
  })

  it('the horizon is a parameter, not a hardcoded year', () => {
    expect(upcomingMoments(MOMENTS, NOW, { horizonDays: 500 }).map(m => m.key)).toEqual(['soon', 'mid', 'far'])
    expect(upcomingMoments(MOMENTS, NOW, { horizonDays: 0 })).toEqual([])
  })

  it('atRisk is the actionable subset — the reason this is not a calendar widget', () => {
    const risky = atRisk(MOMENTS, NOW)
    expect(risky.map(m => m.key)).toEqual(['soon'])
    expect(risky[0].plan.slackDays).toBeLessThan(0)
  })

  it('every returned moment carries its plan', () => {
    for (const m of upcomingMoments(MOMENTS, NOW)) {
      expect(m.plan.stages).toHaveLength(STAGES.length)
    }
  })

  it('junk input yields an empty window rather than throwing', () => {
    expect(upcomingMoments(undefined, NOW)).toEqual([])
    expect(upcomingMoments([{ key: 'nodate' }], NOW)).toEqual([])
    expect(atRisk(null, NOW)).toEqual([])
  })
})
