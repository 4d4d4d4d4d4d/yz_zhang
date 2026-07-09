import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

// Spec 22 — the architecture rules of spec 00 §2 and spec 13 rule 2,
// enforced as static source checks instead of prose.

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const LOGIC_DIR = join(ROOT, 'src/logic')
const SPECS_DIR = join(ROOT, '..', 'docs/specs')

const logicFiles = readdirSync(LOGIC_DIR).filter(f => f.endsWith('.js'))
const sourceOf = f => readFileSync(join(LOGIC_DIR, f), 'utf8')

describe('logic-layer isolation (spec 00 §2)', () => {
  it('covers the whole logic layer', () => {
    expect(logicFiles.length).toBeGreaterThanOrEqual(20)
  })

  for (const file of logicFiles) {
    it(`${file} imports nothing (except the sanctioned ./core.js)`, () => {
      const violations = []
      sourceOf(file).split('\n').forEach((line, i) => {
        const importish = /^\s*import\s/.test(line) || /\brequire\s*\(/.test(line)
        if (importish && !/from\s+['"]\.\/core\.js['"]/.test(line)) {
          violations.push(`${file}:${i + 1}  ${line.trim()}`)
        }
      })
      expect(violations, violations.join('\n')).toEqual([])
    })
  }
})

describe('RNG/time injection rule (spec 13 rule 2)', () => {
  // Sanctioned forms (spec 22 R1): `= Math.random` as a function REFERENCE
  // (no call parens — a body call always has them), and an injected time
  // parameter conventionally named `now`.
  const stripSanctioned = src => src
    .replace(/=\s*Math\.random\b(?!\s*\()/g, '= __INJECTED__')
    .replace(/\bnow\s*=\s*Date\.now\(\)/g, 'now = __INJECTED__')

  for (const file of logicFiles) {
    it(`${file} has no hardcoded Math.random / Date.now outside default params`, () => {
      const violations = []
      stripSanctioned(sourceOf(file)).split('\n').forEach((line, i) => {
        if (/Math\.random|Date\.now/.test(line)) violations.push(`${file}:${i + 1}  ${line.trim()}`)
      })
      expect(violations, violations.join('\n')).toEqual([])
    })
  }
})

describe('specs index consistency', () => {
  const index = readFileSync(join(SPECS_DIR, 'README.md'), 'utf8')

  it('every markdown link in the index resolves to an existing spec', () => {
    const missing = []
    for (const [, target] of index.matchAll(/\]\((\d\d-[\w-]+\.md)\)/g)) {
      if (!existsSync(join(SPECS_DIR, target))) missing.push(target)
    }
    expect(missing, missing.join(', ')).toEqual([])
  })

  it('every logic/tests path referenced in the index exists on disk', () => {
    const missing = []
    for (const [, ref] of index.matchAll(/`((?:logic|tests)\/[\w.]+\.js)`/g)) {
      const path = ref.startsWith('logic/')
        ? join(ROOT, 'src', ref)
        : join(ROOT, ref)
      if (!existsSync(path)) missing.push(ref)
    }
    expect(missing, missing.join(', ')).toEqual([])
  })
})
