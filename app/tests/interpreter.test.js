import { describe, it, expect } from 'vitest'
import { applyGlossary, routeCaption, pairLatencyMs } from '../src/logic/interpreter.js'

const GLOSSARY = [
  { term: 'AdForge', keep: true },
  { term: 'AdForge Studio', keep: true },
  { term: 'trust link', translations: { zh: '信任链接', de: 'Trust-Link' } }
]

describe('applyGlossary', () => {
  it('longest match wins: "AdForge Studio" stays whole', () => {
    const r = applyGlossary('Open AdForge Studio now', GLOSSARY, 'zh')
    expect(r.text).toContain('AdForge Studio')
    expect(r.protected.some(p => p.term === 'AdForge Studio')).toBe(true)
  })

  it('keep-terms survive translation and case is normalized to the fixed form', () => {
    const r = applyGlossary('ADFORGE is great', GLOSSARY, 'de')
    expect(r.text).toBe('AdForge is great')
  })

  it('translated terms use the per-language fixed form', () => {
    expect(applyGlossary('share a trust link', GLOSSARY, 'zh').text).toBe('share a 信任链接')
    expect(applyGlossary('share a trust link', GLOSSARY, 'de').text).toBe('share a Trust-Link')
  })

  it('no glossary → text unchanged, nothing protected', () => {
    const r = applyGlossary('plain text', [], 'zh')
    expect(r).toEqual({ text: 'plain text', protected: [] })
  })
})

describe('pairLatencyMs', () => {
  it('same language is 0; cross-family slower than same-family', () => {
    expect(pairLatencyMs('en', 'en', 50)).toBe(0)
    const sameFam = pairLatencyMs('en', 'es', 50)
    const crossFam = pairLatencyMs('en', 'zh', 50)
    expect(crossFam).toBeGreaterThan(sameFam)
  })

  it('is deterministic', () => {
    expect(pairLatencyMs('ja', 'de', 80)).toBe(pairLatencyMs('ja', 'de', 80))
  })
})

describe('routeCaption', () => {
  const session = { participants: [
    { id: 'a', lang: 'zh' }, { id: 'b', lang: 'en' }, { id: 'c', lang: 'en' }, { id: 'd', lang: 'de' }
  ] }

  it('fans out to everyone except the speaker', () => {
    const caps = routeCaption({ speakerId: 'a', lang: 'zh', text: '你好' }, session)
    expect(caps).toHaveLength(3)
    expect(caps.map(c => c.to)).toEqual(['b', 'c', 'd'])
  })

  it('same-language listeners get verbatim with zero latency', () => {
    const caps = routeCaption({ speakerId: 'b', lang: 'en', text: 'hello' }, session)
    const toC = caps.find(c => c.to === 'c')
    expect(toC.verbatim).toBe(true)
    expect(toC.latencyMs).toBe(0)
  })

  it('cross-language captions carry latency and glossary protection', () => {
    const caps = routeCaption({ speakerId: 'b', lang: 'en', text: 'send the trust link' }, session, GLOSSARY)
    const toA = caps.find(c => c.to === 'a')
    expect(toA.verbatim).toBe(false)
    expect(toA.latencyMs).toBeGreaterThan(0)
    expect(toA.text).toContain('信任链接')
  })
})
