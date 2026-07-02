import { describe, it, expect } from 'vitest'
import {
  trustScore, createTrustLink, validateTrustLink, revokeTrustLink,
  generateToken, createQueue, MAX_LINK_DAYS
} from '../src/logic/showcase.js'

describe('trustScore', () => {
  it('full evidence → 100 / verified', () => {
    const r = trustScore({ provenance: true, metricsVerified: true, clientAttested: true, complianceGate: true })
    expect(r.score).toBe(100)
    expect(r.badge).toBe('verified')
  })

  it('tier boundaries follow the spec (≥85 verified, ≥60 substantiated)', () => {
    // provenance(35) + metrics(25) = 60 → substantiated
    expect(trustScore({ provenance: true, metricsVerified: true }).badge).toBe('substantiated')
    // provenance + metrics + compliance = 80 → still substantiated
    expect(trustScore({ provenance: true, metricsVerified: true, complianceGate: true }).badge).toBe('substantiated')
    // + clientAttested(20) → 100 verified; nothing → claimed
    expect(trustScore({}).badge).toBe('claimed')
  })
})

describe('trust links', () => {
  it('clamps expiry into [1, MAX_LINK_DAYS] and filters unknown scopes', () => {
    const l = createTrustLink({ reelIds: ['r1'], scopes: ['assets', 'bogus'], expiresInDays: 9999, now: 0 })
    expect(l.expiresAt).toBe(MAX_LINK_DAYS * 86400000)
    expect(l.scopes).toEqual(['assets'])
  })

  it('refuses to disable the watermark when assets are exposed', () => {
    expect(() => createTrustLink({ reelIds: ['r1'], scopes: ['assets'], watermark: false }))
      .toThrow(/watermark/)
    // …but allows it when assets are not in scope
    expect(() => createTrustLink({ reelIds: ['r1'], scopes: ['metrics'], watermark: false })).not.toThrow()
  })

  it('validates expiry, revocation, and malformed links', () => {
    const l = createTrustLink({ reelIds: ['r1'], expiresInDays: 1, now: 0 })
    expect(validateTrustLink(l, 1000).valid).toBe(true)
    expect(validateTrustLink(l, 86400000)).toEqual({ valid: false, reason: 'expired' })
    revokeTrustLink(l)
    expect(validateTrustLink(l, 1000)).toEqual({ valid: false, reason: 'revoked' })
    expect(validateTrustLink({ token: 'short' }, 0).reason).toBe('malformed')
    expect(validateTrustLink(null, 0).reason).toBe('malformed')
  })

  it('generates unique 24-char tokens across 1k draws', () => {
    const seen = new Set()
    for (let i = 0; i < 1000; i++) seen.add(generateToken())
    expect(seen.size).toBe(1000)
    expect([...seen][0]).toHaveLength(24)
  })

  it('token generation is deterministic under an injected RNG', () => {
    let s = 42
    const lcg = () => (s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296
    let s2 = 42
    const lcg2 = () => (s2 = (s2 * 1664525 + 1013904223) % 4294967296) / 4294967296
    expect(generateToken(lcg)).toBe(generateToken(lcg2))
  })
})

describe('verification queue', () => {
  const delay = ms => new Promise(r => setTimeout(r, ms))

  it('never exceeds the concurrency limit under burst', async () => {
    const q = createQueue(2)
    let inFlight = 0, peak = 0
    const task = async () => {
      inFlight++; peak = Math.max(peak, inFlight)
      await delay(10)
      inFlight--
    }
    await Promise.all(Array.from({ length: 12 }, () => q.enqueue(task)))
    expect(peak).toBe(2)
    expect(q.stats()).toMatchObject({ inFlight: 0, queued: 0, done: 12, failed: 0 })
  })

  it('runs higher priority first, FIFO within a class', async () => {
    const q = createQueue(1)
    const order = []
    const mk = name => async () => { order.push(name); await delay(1) }
    const first = q.enqueue(mk('running'))
    const jobs = [
      q.enqueue(mk('low-1'), { priority: 1 }),
      q.enqueue(mk('low-2'), { priority: 1 }),
      q.enqueue(mk('high-1'), { priority: 3 }),
      q.enqueue(mk('high-2'), { priority: 3 })
    ]
    await Promise.all([first, ...jobs])
    expect(order).toEqual(['running', 'high-1', 'high-2', 'low-1', 'low-2'])
  })

  it('a failing task rejects only its caller and releases the slot', async () => {
    const q = createQueue(1)
    const boom = q.enqueue(async () => { throw new Error('boom') })
    const ok = q.enqueue(async () => 'fine')
    await expect(boom).rejects.toThrow('boom')
    await expect(ok).resolves.toBe('fine')
    expect(q.stats()).toMatchObject({ done: 1, failed: 1, inFlight: 0, queued: 0 })
  })

  it('rejects invalid limits', () => {
    expect(() => createQueue(0)).toThrow()
    expect(() => createQueue(1.5)).toThrow()
  })
})
