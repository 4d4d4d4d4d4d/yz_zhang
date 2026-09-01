#!/usr/bin/env node
// Spec 28 — build-and-measure wrapper around the pure budget evaluator.
import { readdirSync, readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'
import { evaluateBudget, TOTAL_BUDGET } from '../src/logic/bundleBudget.js'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const assetsDir = join(root, 'dist', 'assets')

if (!existsSync(assetsDir)) {
  console.error('dist/assets not found — run `npm run build` first.')
  process.exit(1)
}

const chunks = readdirSync(assetsDir)
  .filter(f => f.endsWith('.js'))
  .map(f => ({
    name: f,
    gzipKB: Math.round(gzipSync(readFileSync(join(assetsDir, f))).length / 1024 * 100) / 100
  }))
  .sort((a, b) => b.gzipKB - a.gzipKB)

const { ok, violations, totalKB, paths } = evaluateBudget(chunks)

console.log('Bundle gzip sizes (KB):')
for (const c of chunks) console.log(`  ${c.gzipKB.toFixed(1).padStart(7)}  ${c.name}`)
console.log(`  ${totalKB.toFixed(1).padStart(7)}  (total, budget ${TOTAL_BUDGET})`)

// Spec 59 — the number that describes a real reader, not the sum nobody downloads.
console.log('\nDelivered per path (gzip KB):')
for (const [name, p] of Object.entries(paths)) {
  const via = p.heaviest ? ` (worst section: ${p.heaviest})` : ''
  console.log(`  ${p.kb.toFixed(1).padStart(7)}  ${name}, budget ${p.limit}${via}`)
}

if (!ok) {
  console.error('\n✗ Bundle budget exceeded:')
  for (const v of violations) console.error(`  ${v.name}: ${v.gzipKB} KB > ${v.limit} KB (over by ${v.overBy} KB)`)
  process.exit(1)
}
console.log('\n✓ All chunks within budget.')
