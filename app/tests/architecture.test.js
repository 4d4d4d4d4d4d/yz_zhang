import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname, sep } from 'node:path'
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

// ---------------------------------------------------------------- spec 55
// Specs 50/51 found engines that were fully built and fully tested but wired
// to nothing: recommend.js (the flagship "explainable" ranker) and
// marketing.js. Both had shipped to no user. That audit was manual; this
// makes it permanent, so a logic module cannot be written without either a
// consumer in the app or an explicit, verified exemption.

// Modules legitimately consumed outside src/ (build tooling, not the app).
const CONSUMER_EXEMPT = { 'bundleBudget.js': 'scripts/check-bundle.mjs' }

function walk(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) walk(full, out)
    else out.push(full)
  }
  return out
}

describe('logic modules are wired and tested (spec 55)', () => {
  const SRC = join(ROOT, 'src')
  const TESTS = join(ROOT, 'tests')

  // Everything in src/ that is NOT itself part of the logic layer.
  const appSources = walk(SRC)
    .filter(f => !f.includes(`${sep}logic${sep}`))
    .map(f => readFileSync(f, 'utf8'))

  const testSources = walk(TESTS).map(f => readFileSync(f, 'utf8'))

  for (const file of logicFiles) {
    it(`${file} is consumed by the app`, () => {
      const needle = `logic/${file}`
      if (CONSUMER_EXEMPT[file]) {
        const exemptPath = join(ROOT, CONSUMER_EXEMPT[file])
        expect(existsSync(exemptPath), `${file}: exemption points at a missing file`).toBe(true)
        expect(
          readFileSync(exemptPath, 'utf8').includes(needle),
          `${file}: exempted to ${CONSUMER_EXEMPT[file]}, which does not reference it`
        ).toBe(true)
        return
      }
      expect(
        appSources.some(src => src.includes(needle)),
        `${file} has no consumer in src/ — an engine wired to nothing ships to nobody`
      ).toBe(true)
    })

    it(`${file} is covered by a test file`, () => {
      expect(
        testSources.some(src => src.includes(`logic/${file}`)),
        `${file} is not referenced by any test`
      ).toBe(true)
    })
  }
})
