// Spec 28 — pure bundle-budget evaluation (the build-and-measure wrapper
// lives in scripts/check-bundle.mjs; this is the tested decision logic).
//
// Spec 59 revision. When everything shipped in two chunks, "sum of all chunks"
// was a fair proxy for what a visitor downloads. Code-splitting the console by
// section broke that equivalence: the sum went UP (7.5 KB of lost cross-chunk
// compression) while the bytes a reader actually receives to open a console
// section went DOWN by ~76%. A budget that only watches the sum would score
// that as a regression and quietly push the codebase back toward one big
// chunk. So the sum is kept as a coarse anti-bloat ceiling, and the real
// guard is now per-path: what one reader downloads to see one surface.

// gzip KB budgets, matched by filename prefix (vite names chunks
// `<Name>-<hash>.js`). Unlisted chunks fall under DEFAULT.
export const SECTION_KEYS = ['recommend', 'marketing', 'partners', 'deals', 'showcase', 'immersive', 'trust', 'markets']
export const SECTION_BUDGET = 22 // no single console section may outgrow its peers

export const BUDGETS = {
  index: 100,  // shared app shell + router + fallback locale
  Console: 20, // console SHELL only — panels ship per section (spec 59)
  ...Object.fromEntries(SECTION_KEYS.map(k => [k, SECTION_BUDGET])),
  DEFAULT: 40
}
// Anti-bloat ceiling across ALL JS assets. Nobody downloads this number, so it
// is deliberately loose and gets raised when a genuinely new surface lands
// (spec 60's `markets` section took it past 250). The number that must NOT
// drift is `PATHS` below — what one reader actually receives. Raising TOTAL
// while a path budget also rises is the signal to stop and split something.
export const TOTAL_BUDGET = 285

// What a reader actually downloads for a surface. Declared, not inferred: the
// point is to state the claim ("opening the console costs at most X") and let
// CI check it, rather than to re-derive the module graph here.
export const PATHS = {
  // Worst case: entry + console shell + the heaviest single section.
  console: { include: ['index', 'Console'], worstOf: SECTION_KEYS, budget: 130 },
  // A marketing-site visitor never touches console code at all.
  landing: { include: ['index', 'Home'], worstOf: [], budget: 110 }
}

export function budgetFor(name, budgets = BUDGETS) {
  for (const key of Object.keys(budgets)) {
    if (key !== 'DEFAULT' && name.startsWith(key)) return budgets[key]
  }
  return budgets.DEFAULT
}

const round2 = n => Math.round(n * 100) / 100
const sizeOf = (chunks, prefix) =>
  chunks.filter(c => c.name.startsWith(prefix)).reduce((s, c) => s + c.gzipKB, 0)

// Cost of one declared path: the always-included chunks plus the single
// heaviest of the alternatives (a reader opens one section, not all seven).
export function pathCost(chunks = [], path = { include: [], worstOf: [] }) {
  const base = (path.include ?? []).reduce((s, p) => s + sizeOf(chunks, p), 0)
  const worst = (path.worstOf ?? []).reduce((max, p) => Math.max(max, sizeOf(chunks, p)), 0)
  const heaviest = (path.worstOf ?? []).reduce(
    (best, p) => (sizeOf(chunks, p) > sizeOf(chunks, best ?? p) || best === null ? p : best), null)
  return { kb: round2(base + worst), base: round2(base), worst: round2(worst), heaviest: worst > 0 ? heaviest : null }
}

// chunks: [{ name, gzipKB }]. Returns { ok, violations, totalKB, paths }.
export function evaluateBudget(chunks = [], { budgets = BUDGETS, total = TOTAL_BUDGET, paths = PATHS } = {}) {
  const violations = []
  let totalKB = 0
  for (const c of chunks) {
    totalKB += c.gzipKB
    const limit = budgetFor(c.name, budgets)
    if (c.gzipKB > limit) {
      violations.push({ name: c.name, gzipKB: c.gzipKB, limit, overBy: round2(c.gzipKB - limit) })
    }
  }
  totalKB = round2(totalKB)
  if (totalKB > total) {
    violations.push({ name: '(total)', gzipKB: totalKB, limit: total, overBy: round2(totalKB - total) })
  }

  const pathReport = {}
  for (const [name, path] of Object.entries(paths)) {
    const cost = pathCost(chunks, path)
    pathReport[name] = { ...cost, limit: path.budget }
    if (cost.kb > path.budget) {
      violations.push({
        name: `(path: ${name}${cost.heaviest ? ` via ${cost.heaviest}` : ''})`,
        gzipKB: cost.kb,
        limit: path.budget,
        overBy: round2(cost.kb - path.budget)
      })
    }
  }

  return { ok: violations.length === 0, violations, totalKB, paths: pathReport }
}
