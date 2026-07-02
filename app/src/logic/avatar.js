// Spec 07 — digital human marketing video: storyboard planning,
// platform caps, multi-language variants. Synthetic-media disclosure
// is unconditional.

export const PERSONAS = [
  { id: 'mira',  name: 'Mira',  style: 'host',     languages: ['en', 'es', 'ja'] },
  { id: 'kenji', name: 'Kenji', style: 'engineer', languages: ['ja', 'en', 'zh'] },
  { id: 'lena',  name: 'Lena',  style: 'founder',  languages: ['en', 'de', 'es'] },
  { id: 'wei',   name: 'Wei',   style: 'host',     languages: ['zh', 'en', 'ja'] }
]

export const PLATFORM_CAPS = { tiktok: 60, shorts: 60, meta: 90, web: 180 }

const CJK = new Set(['zh', 'ja', 'ko'])
const GESTURES = ['open-palm', 'point', 'nod', 'lean-in']

function splitSentences(script) {
  return String(script || '')
    .split(/(?<=[.!?。！？；;])\s*/)
    .map(s => s.trim())
    .filter(Boolean)
}

// CJK reads ~5 chars/s; latin ~2.6 words/s. Clamped 1.5–8 s per scene.
export function estimateSeconds(text, language) {
  if (!text) return 0
  const raw = CJK.has(language)
    ? text.replace(/\s/g, '').length / 5
    : text.split(/\s+/).filter(Boolean).length / 2.6
  return Math.min(8, Math.max(1.5, Math.round(raw * 10) / 10))
}

export function planStoryboard(script, { persona = 'mira', language = 'en', platform = 'web' } = {}) {
  const cap = PLATFORM_CAPS[platform] ?? PLATFORM_CAPS.web
  const sentences = splitSentences(script)
  const scenes = sentences.map((text, idx) => ({
    idx,
    text,
    seconds: estimateSeconds(text, language),
    gesture: GESTURES[idx % GESTURES.length],
    lipSync: Math.max(1, Math.round(text.replace(/\s/g, '').length / 3)) // phoneme-group hint
  }))

  // Truncate at scene boundaries only.
  const kept = []
  const dropped = []
  let total = 0
  for (const sc of scenes) {
    if (total + sc.seconds <= cap) { kept.push(sc); total += sc.seconds }
    else dropped.push(sc)
  }
  return {
    persona,
    language,
    platform,
    scenes: kept,
    dropped,
    truncated: dropped.length > 0,
    totalSeconds: Math.round(total * 10) / 10,
    cap,
    disclosure: 'synthetic-media' // legal floor — not configurable
  }
}

export function localizeVariants(plan, languages = []) {
  const persona = PERSONAS.find(p => p.id === plan.persona)
  const supported = new Set(persona ? persona.languages : [])
  const variants = []
  const skipped = []
  for (const lang of languages) {
    if (!supported.has(lang)) { skipped.push(lang); continue }
    const scenes = plan.scenes.map(sc => ({ ...sc, seconds: estimateSeconds(sc.text, lang) }))
    variants.push({
      ...plan,
      language: lang,
      scenes,
      totalSeconds: Math.round(scenes.reduce((s, sc) => s + sc.seconds, 0) * 10) / 10
    })
  }
  return { variants, skipped }
}
