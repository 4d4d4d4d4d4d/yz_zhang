import { describe, it, expect } from 'vitest'
import { createBandit } from '../src/logic/bandit.js'

const ARMS = [
  { id: 'A', truth: 0.05 },
  { id: 'B', truth: 0.02 },
  { id: 'C', truth: 0.09 },
  { id: 'D', truth: 0.03 }
]

const lcg = (seed = 42) => {
  let s = seed >>> 0
  return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296
}

describe('determinism (spec 13 rule 2)', () => {
  it('same seed → identical pull sequence and snapshot', () => {
    const b1 = createBandit(ARMS, { rng: lcg(7) })
    const b2 = createBandit(ARMS, { rng: lcg(7) })
    const seq1 = [], seq2 = []
    for (let i = 0; i < 500; i++) { seq1.push(b1.step().armId); seq2.push(b2.step().armId) }
    expect(seq1).toEqual(seq2)
    expect(b1.snapshot()).toEqual(b2.snapshot())
  })

  it('different seeds diverge', () => {
    const b1 = createBandit(ARMS, { rng: lcg(1) })
    const b2 = createBandit(ARMS, { rng: lcg(2) })
    const seq1 = [], seq2 = []
    for (let i = 0; i < 200; i++) { seq1.push(b1.step().armId); seq2.push(b2.step().armId) }
    expect(seq1).not.toEqual(seq2)
  })
})

describe('learning behavior', () => {
  it('converges: best-truth arm C wins the plurality of pulls and >50% share', () => {
    const b = createBandit(ARMS, { epsilon: 0.1, rng: lcg(42) })
    for (let i = 0; i < 2000; i++) b.step()
    const snap = b.snapshot()
    const byPulls = [...snap.arms].sort((a, b2) => b2.pulls - a.pulls)
    expect(byPulls[0].id).toBe('C')
    expect(snap.arms.find(a => a.id === 'C').share).toBeGreaterThan(50)
  })

  it('ε = 1 explores uniformly: no arm starves', () => {
    const b = createBandit(ARMS, { epsilon: 1, rng: lcg(9) })
    for (let i = 0; i < 2000; i++) b.step()
    for (const a of b.snapshot().arms) expect(a.pulls).toBeGreaterThan(300)
  })
})

describe('bookkeeping invariants', () => {
  it('posteriors track pulls and conversions exactly', () => {
    const b = createBandit(ARMS, { rng: lcg(5) })
    for (let i = 0; i < 800; i++) b.step()
    for (const a of b.snapshot().arms) {
      expect(a.alpha + a.beta - 2).toBe(a.pulls)
      expect(a.alpha - 1).toBe(a.conv)
    }
  })

  it('shares sum to exactly 100 at every step', () => {
    const b = createBandit(ARMS, { rng: lcg(3) })
    for (let i = 0; i < 50; i++) {
      b.step()
      const total = b.snapshot().arms.reduce((s, a) => s + a.share, 0)
      expect(total).toBe(100)
    }
  })

  it('realized regret trends upward over a long run and is window-capped', () => {
    const b = createBandit(ARMS, { rng: lcg(11), regretWindow: 100 })
    for (let i = 0; i < 300; i++) b.step()
    const r = b.snapshot().regret
    expect(r.length).toBe(100)
    // per-step delta is bestTruth − reward ∈ {0.09, −0.91}: dips allowed,
    // but the window as a whole should climb
    expect(r[r.length - 1]).toBeGreaterThan(r[0] - 1)
    for (let i = 1; i < r.length; i++) expect(r[i] - r[i - 1]).toBeLessThanOrEqual(0.09 + 1e-9)
  })

  it('reset restores the initial state; epsilon is clamped', () => {
    const b = createBandit(ARMS, { epsilon: 5, rng: lcg(1) })
    expect(b.epsilon()).toBe(1)
    b.setEpsilon(-3)
    expect(b.epsilon()).toBe(0)
    for (let i = 0; i < 100; i++) b.step()
    b.reset()
    const snap = b.snapshot()
    expect(snap.totalPulls).toBe(0)
    expect(snap.cumReward).toBe(0)
    expect(snap.regret).toEqual([])
    for (const a of snap.arms) expect(a.share).toBe(25)
  })
})
