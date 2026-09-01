// Spec 35 — binds sortRows to reactive table state and exposes the aria-sort
// value headers need. `rows` may be a ref or a computed (e.g. a filtered list).

import { ref, computed, unref } from 'vue'
import { sortRows, nextDir } from '../logic/sortRows.js'

export function useSortable(rows, { key = null, dir = 'asc' } = {}) {
  const sortKey = ref(key)
  const sortDir = ref(dir)

  const sorted = computed(() => sortRows(unref(rows), sortKey.value, sortDir.value))

  function sortBy(k) {
    sortDir.value = nextDir(sortKey.value, k, sortDir.value)
    sortKey.value = k
  }

  // WAI-ARIA sort state for the active column; 'none' otherwise.
  function ariaSort(k) {
    if (sortKey.value !== k) return 'none'
    return sortDir.value === 'asc' ? 'ascending' : 'descending'
  }

  return { sortKey, sortDir, sorted, sortBy, ariaSort }
}
