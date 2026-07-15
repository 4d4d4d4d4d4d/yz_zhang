// Spec 28 — pure bundle-budget evaluation (the build-and-measure wrapper
// lives in scripts/check-bundle.mjs; this is the tested decision logic).

// gzip KB budgets. Entry match is by filename prefix (vite names chunks
// `<Name>-<hash>.js`). Unlisted chunks fall under DEFAULT.
export const BUDGETS = {
  index: 100,   // current ~81 gz
  Console: 110, // current ~90 gz — the heaviest chunk
  DEFAULT: 40
}
export const TOTAL_BUDGET = 250 // gzip KB across all JS assets (current ~195)

export function budgetFor(name, budgets = BUDGETS) {
  for (const key of Object.keys(budgets)) {
    if (key !== 'DEFAULT' && name.startsWith(key)) return budgets[key]
  }
  return budgets.DEFAULT
}

// chunks: [{ name, gzipKB }]. Returns { ok, violations, totalKB }.
export function evaluateBudget(chunks = [], { budgets = BUDGETS, total = TOTAL_BUDGET } = {}) {
  const violations = []
  let totalKB = 0
  for (const c of chunks) {
    totalKB += c.gzipKB
    const limit = budgetFor(c.name, budgets)
    if (c.gzipKB > limit) {
      violations.push({ name: c.name, gzipKB: c.gzipKB, limit, overBy: Math.round((c.gzipKB - limit) * 100) / 100 })
    }
  }
  totalKB = Math.round(totalKB * 100) / 100
  if (totalKB > total) {
    violations.push({ name: '(total)', gzipKB: totalKB, limit: total, overBy: Math.round((totalKB - total) * 100) / 100 })
  }
  return { ok: violations.length === 0, violations, totalKB }
}
