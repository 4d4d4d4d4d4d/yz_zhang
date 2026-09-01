import { describe, it, expect } from 'vitest'
import {
  matchSpecialists, createCase, advanceCase, addEvidence, verifyChain, CASE_STATES
} from '../src/logic/fieldVerify.js'

const SPECIALISTS = [
  { id: 's1', country: 'JP', crossBorder: [], languages: ['ja', 'en'], expertise: ['manufacturing'], availableInDays: 3, rating: 4.9 },
  { id: 's2', country: 'KR', crossBorder: ['JP'], languages: ['ko', 'en'], expertise: ['manufacturing', 'quality'], availableInDays: 5, rating: 4.7 },
  { id: 's3', country: 'BR', crossBorder: [], languages: ['pt'], expertise: ['licensing'], availableInDays: 1, rating: 5.0 }
]

describe('matchSpecialists', () => {
  const req = { country: 'JP', languages: ['en', 'ja'], expertise: ['manufacturing'], urgencyDays: 7 }

  it('country coverage is a hard filter (resident or licensed cross-border)', () => {
    const ids = matchSpecialists(req, SPECIALISTS).map(m => m.specialist.id)
    expect(ids).toContain('s1')
    expect(ids).toContain('s2') // cross-border JP
    expect(ids).not.toContain('s3')
  })

  it('scores by weighted language/expertise/availability', () => {
    const [top] = matchSpecialists(req, SPECIALISTS)
    expect(top.specialist.id).toBe('s1') // full lang overlap beats s2's half
    expect(top.score).toBe(100)
  })

  it('urgency credit tiers: within → 1, within 2× → 0.5, beyond → 0', () => {
    const mk = days => matchSpecialists({ ...req, urgencyDays: days }, [SPECIALISTS[0]])[0].factors.availability
    expect(mk(3)).toBe(1)
    expect(mk(2)).toBe(0.5)  // available in 3 ≤ 2×2=4
    expect(mk(1)).toBe(0)    // 3 > 2
  })

  it('no coverage → empty result, never a remote assignment', () => {
    expect(matchSpecialists({ ...req, country: 'DE' }, SPECIALISTS)).toEqual([])
  })
})

describe('case workflow', () => {
  it('walks the full happy path with an audit entry per transition', () => {
    const k = createCase({ id: 'c1', country: 'JP', subject: 'audit' })
    advanceCase(k, 'assigned'); advanceCase(k, 'on-site')
    addEvidence(k, { type: 'photo', ref: 'p1' }, 1000)
    advanceCase(k, 'evidence-collected'); advanceCase(k, 'report-drafted')
    expect(advanceCase(k, 'attested').ok).toBe(true)
    expect(advanceCase(k, 'closed').ok).toBe(true)
    expect(k.state).toBe('closed')
    expect(k.audit).toHaveLength(6)
    expect(k.audit[0]).toMatchObject({ from: 'requested', to: 'assigned' })
  })

  it('rejects skips and regressions without mutating the case', () => {
    const k = createCase({ id: 'c2' })
    expect(advanceCase(k, 'on-site').ok).toBe(false)      // skip
    advanceCase(k, 'assigned')
    expect(advanceCase(k, 'requested').ok).toBe(false)     // regression
    expect(advanceCase(k, 'bogus').ok).toBe(false)         // unknown
    expect(k.state).toBe('assigned')
    expect(k.audit).toHaveLength(1)
  })

  it('attestation requires non-empty, intact evidence', () => {
    const k = createCase({ id: 'c3' })
    for (const s of ['assigned', 'on-site', 'evidence-collected', 'report-drafted']) advanceCase(k, s)
    expect(advanceCase(k, 'attested')).toMatchObject({ ok: false, reason: 'attestation requires evidence' })
    addEvidence(k, { type: 'photo', ref: 'p1' }, 1)
    k.evidence[0].ref = 'tampered'
    expect(advanceCase(k, 'attested').ok).toBe(false)
    expect(k.state).toBe('report-drafted')
  })
})

describe('evidence chain', () => {
  it('is valid after several adds and empty chains are valid', () => {
    const k = createCase({ id: 'c4' })
    expect(verifyChain(k).valid).toBe(true)
    addEvidence(k, { type: 'photo', ref: 'a' }, 1)
    addEvidence(k, { type: 'scan', ref: 'b' }, 2)
    addEvidence(k, { type: 'video', ref: 'c' }, 3)
    expect(verifyChain(k)).toEqual({ valid: true, brokenAt: null })
  })

  it('tampering with item k breaks the chain at k', () => {
    const k = createCase({ id: 'c5' })
    addEvidence(k, { type: 'photo', ref: 'a' }, 1)
    addEvidence(k, { type: 'scan', ref: 'b' }, 2)
    addEvidence(k, { type: 'video', ref: 'c' }, 3)
    k.evidence[1].ref = 'evil'
    const r = verifyChain(k)
    expect(r.valid).toBe(false)
    expect(r.brokenAt).toBe(1)
  })

  it('links are chained: each item embeds the previous hash', () => {
    const k = createCase({ id: 'c6' })
    const e0 = addEvidence(k, { type: 'photo', ref: 'a' }, 1)
    const e1 = addEvidence(k, { type: 'scan', ref: 'b' }, 2)
    expect(e0.prevHash).toBe('genesis')
    expect(e1.prevHash).toBe(e0.hash)
  })
})
