import { describe, it, expect } from 'vitest'
import { planStoryboard, localizeVariants, estimateSeconds, PLATFORM_CAPS } from '../src/logic/avatar.js'

const LONG_EN = Array.from({ length: 30 }, (_, i) =>
  `Sentence number ${i + 1} carries roughly ten words of marketing copy here.`).join(' ')

describe('estimateSeconds', () => {
  it('uses char-based pace for CJK and word-based for latin', () => {
    const en = estimateSeconds('This sentence has exactly eight words in it.', 'en')
    expect(en).toBeCloseTo(8 / 2.6, 0)
    const zh = estimateSeconds('这句话一共十个字啊', 'zh') // 9 chars ≈ 1.8s
    expect(zh).toBeCloseTo(1.8, 1)
  })

  it('clamps to [1.5, 8] seconds', () => {
    expect(estimateSeconds('Hi.', 'en')).toBe(1.5)
    expect(estimateSeconds('word '.repeat(100), 'en')).toBe(8)
  })
})

describe('planStoryboard', () => {
  it('splits sentences into scenes with non-repeating consecutive gestures', () => {
    const p = planStoryboard('One sentence here. Another one follows! A third arrives? 最後は日本語。')
    expect(p.scenes.length).toBe(4)
    for (let i = 1; i < p.scenes.length; i++) {
      expect(p.scenes[i].gesture).not.toBe(p.scenes[i - 1].gesture)
    }
  })

  it('truncates at scene boundaries under the platform cap and reports drops', () => {
    const p = planStoryboard(LONG_EN, { platform: 'tiktok' })
    expect(p.truncated).toBe(true)
    expect(p.totalSeconds).toBeLessThanOrEqual(PLATFORM_CAPS.tiktok)
    expect(p.dropped.length).toBeGreaterThan(0)
    expect(p.scenes.length + p.dropped.length).toBe(30)
  })

  it('empty script → empty storyboard, no throw', () => {
    const p = planStoryboard('')
    expect(p.scenes).toEqual([])
    expect(p.totalSeconds).toBe(0)
    expect(p.truncated).toBe(false)
  })

  it('synthetic-media disclosure is always present', () => {
    expect(planStoryboard('Hello there, world.').disclosure).toBe('synthetic-media')
    expect(planStoryboard(LONG_EN, { platform: 'meta' }).disclosure).toBe('synthetic-media')
  })
})

describe('localizeVariants', () => {
  const base = planStoryboard('Great products deserve great launches. See it live today.', { persona: 'mira', language: 'en' })

  it('expands supported languages and skips unsupported ones explicitly', () => {
    const { variants, skipped } = localizeVariants(base, ['es', 'ja', 'zh'])
    expect(variants.map(v => v.language)).toEqual(['es', 'ja']) // mira: en/es/ja
    expect(skipped).toEqual(['zh'])
  })

  it('re-estimates duration per language class', () => {
    const { variants } = localizeVariants(base, ['ja'])
    expect(variants[0].totalSeconds).not.toBe(0)
    expect(variants[0].scenes.length).toBe(base.scenes.length)
  })
})
