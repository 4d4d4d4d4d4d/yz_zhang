// Spec 35 — stable, type-aware row sorting for console tables. Pure and
// framework-free. Numbers compare numerically, everything else by string;
// equal keys preserve input order (stable), so re-sorting never scrambles ties.

export function compareVals(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a ?? '').localeCompare(String(b ?? ''))
}

export function sortRows(rows, key, dir = 'asc', accessor = (row, k) => row[k]) {
  if (!Array.isArray(rows)) return []
  if (!key) return rows.slice()
  const sign = dir === 'desc' ? -1 : 1
  return rows
    .map((row, i) => ({ row, i }))
    .sort((x, y) => {
      const c = compareVals(accessor(x.row, key), accessor(y.row, key))
      return c !== 0 ? c * sign : x.i - y.i // stable tiebreak on original index
    })
    .map(e => e.row)
}

// Header-click cycle: a new column starts ascending; the active column
// toggles asc → desc → asc.
export function nextDir(currentKey, key, currentDir) {
  if (currentKey !== key) return 'asc'
  return currentDir === 'asc' ? 'desc' : 'asc'
}
