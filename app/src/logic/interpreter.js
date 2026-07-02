// Spec 08 — cross-language interpreter: glossary protection + caption routing.

// Glossary entry: { term, translations?: {lang: fixed}, keep?: true }.
// Longest-match-first; case-insensitive; `keep` terms are never translated.
export function applyGlossary(text, glossary = [], targetLang = 'en') {
  let out = String(text || '')
  const found = []
  const entries = [...glossary].sort((a, b) => (b.term?.length || 0) - (a.term?.length || 0))
  for (const entry of entries) {
    if (!entry?.term) continue
    const fixed = entry.keep ? entry.term : entry.translations?.[targetLang]
    if (!fixed) continue
    const re = new RegExp(entry.term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
    let hit = false
    out = out.replace(re, () => { hit = true; return fixed })
    if (hit) found.push({ term: entry.term, rendered: fixed })
  }
  return { text: out, protected: found }
}

const FAMILY = { en: 'latin', es: 'latin', de: 'latin', pt: 'latin', zh: 'cjk', ja: 'cjk', ko: 'cjk' }

// Deterministic simulated latency: base + per-char cost, cross-family pairs slower.
export function pairLatencyMs(fromLang, toLang, textLength) {
  if (fromLang === toLang) return 0
  const cross = FAMILY[fromLang] !== FAMILY[toLang]
  return Math.round((cross ? 220 : 140) + textLength * (cross ? 3.2 : 2.1))
}

// Fan an utterance out to one caption per listener.
export function routeCaption(utterance, session, glossary = []) {
  const { speakerId, lang: fromLang, text } = utterance
  const captions = []
  for (const p of session.participants || []) {
    if (p.id === speakerId) continue
    if (p.lang === fromLang) {
      captions.push({ to: p.id, lang: p.lang, text, verbatim: true, latencyMs: 0, protected: [] })
    } else {
      const g = applyGlossary(text, glossary, p.lang)
      captions.push({
        to: p.id,
        lang: p.lang,
        text: g.text,
        verbatim: false,
        latencyMs: pairLatencyMs(fromLang, p.lang, text.length),
        protected: g.protected
      })
    }
  }
  return captions
}
