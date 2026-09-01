# Spec 07 — Digital Human · AI Marketing Video (数字人营销视频)

Status: **Approved** · Review: R1 (2026-07-02) · Domain: `logic/avatar.js`

## Problem

A brand going overseas needs a spokesperson in every market — same face,
same brand voice, native language. Digital-human marketing video turns
one approved script into per-market presenter videos: storyboarded,
timed, lip-sync-planned, and disclosure-compliant (synthetic media must
be labeled per market rules, aligned with spec 05's `provenance`).

## Design

### Personas
`PERSONAS`: id, display name, style (founder / host / engineer),
supported languages. A persona can only render languages it supports.

### `planStoryboard(script, opts)`
- Input: script text, `{ persona, language, platform }`.
- Splits script into sentence segments; each segment becomes a scene:
  `{ idx, text, seconds, gesture }`.
  - Duration model: words / WPM per language class (CJK char-based at
    ~5 chars/s vs. latin word-based at ~2.6 words/s), clamped 1.5–8 s.
  - Gesture cadence cycles a fixed set (open-palm / point / nod / lean-in)
    so consecutive scenes never repeat a gesture.
- Platform caps (`tiktok` 60 s, `shorts` 60 s, `meta` 90 s, `web` 180 s):
  when total exceeds the cap the storyboard is truncated at a scene
  boundary and flagged `truncated: true` with the dropped scenes listed —
  the operator sees exactly what got cut.
- Output includes `totalSeconds`, `disclosure` (always `synthetic-media`
  label — non-negotiable, see review), and `lipSync` markers per scene
  (phoneme-group counts as a render hint).

### `localizeVariants(plan, languages)`
- Expands one plan into per-language variants; unsupported persona
  languages are returned in `skipped[]`, never silently dropped.
- Variant duration re-estimated per language class (a JA read is not an
  EN read).

## Guarantees
- Deterministic; empty script → empty storyboard, zero seconds, no throw.
- Synthetic-media disclosure cannot be disabled by options.
- Truncation only at scene boundaries; `totalSeconds ≤ platform cap`.

## Test plan
- Sentence split & duration classes (EN vs zh/ja) behave per model.
- Cap truncation: boundary cut, flag set, dropped scenes reported.
- Gesture non-repetition across consecutive scenes.
- Unsupported language → skipped[], supported list expands correctly.
- Disclosure present regardless of options.

## Review record — R1
- ✅ Disclosure made unconditional (draft had it as an option — rejected:
  synthetic-media labeling is a legal floor in EU/DSA & several APAC markets).
- ✅ Truncate-at-boundary chosen over hard time cut (no mid-sentence cuts).
- Verdict: **approved**.
