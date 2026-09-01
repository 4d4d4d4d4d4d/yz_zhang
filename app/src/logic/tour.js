// Spec 09 — virtual factory tour: station graph, validation, BFS
// navigation, coverage, adaptive rendition.

export function validateTour(tour = {}) {
  const stations = tour.stations || []
  const problems = []
  const ids = new Set()
  for (const s of stations) {
    if (ids.has(s.id)) problems.push({ kind: 'duplicate-id', station: s.id })
    ids.add(s.id)
  }
  for (const s of stations) {
    for (const h of s.hotspots || []) {
      if (!ids.has(h.to)) problems.push({ kind: 'dangling-hotspot', station: s.id, to: h.to })
    }
  }
  if (tour.entrance && ids.has(tour.entrance)) {
    const reachable = reachableFrom(tour, tour.entrance)
    for (const s of stations) {
      if (!reachable.has(s.id)) problems.push({ kind: 'unreachable', station: s.id })
    }
  } else if (stations.length) {
    problems.push({ kind: 'missing-entrance', station: tour.entrance ?? null })
  }
  return { ok: problems.length === 0, problems }
}

function reachableFrom(tour, start) {
  const byId = new Map((tour.stations || []).map(s => [s.id, s]))
  const seen = new Set([start])
  const q = [start]
  while (q.length) {
    const cur = byId.get(q.shift())
    for (const h of cur?.hotspots || []) {
      if (byId.has(h.to) && !seen.has(h.to)) { seen.add(h.to); q.push(h.to) }
    }
  }
  return seen
}

// BFS hop-count path along walkways; null when unreachable.
export function shortestPath(tour, from, to) {
  const byId = new Map((tour.stations || []).map(s => [s.id, s]))
  if (!byId.has(from) || !byId.has(to)) return null
  if (from === to) return [from]
  const prev = new Map([[from, null]])
  const q = [from]
  while (q.length) {
    const cur = q.shift()
    for (const h of byId.get(cur)?.hotspots || []) {
      if (!byId.has(h.to) || prev.has(h.to)) continue
      prev.set(h.to, cur)
      if (h.to === to) {
        const path = [to]
        let p = cur
        while (p !== null) { path.unshift(p); p = prev.get(p) }
        return path
      }
      q.push(h.to)
    }
  }
  return null
}

export function coverage(visited = [], tour = {}) {
  const stations = tour.stations || []
  if (!stations.length) return { percent: 0, zones: {}, missed: [] }
  const seen = new Set(visited)
  const zones = {}
  const missed = []
  for (const s of stations) {
    const z = zones[s.zone] || (zones[s.zone] = { total: 0, visited: 0 })
    z.total++
    if (seen.has(s.id)) z.visited++
    else missed.push({ id: s.id, name: s.name, zone: s.zone })
  }
  const percent = Math.round((stations.filter(s => seen.has(s.id)).length / stations.length) * 100)
  return { percent, zones, missed }
}

// Highest rendition whose minMbps fits; lowest as floor — degrade, never deny.
export function pickRendition(bandwidthMbps, renditions = []) {
  if (!renditions.length) return null
  const sorted = [...renditions].sort((a, b) => a.minMbps - b.minMbps)
  let pick = sorted[0]
  for (const r of sorted) if (bandwidthMbps >= r.minMbps) pick = r
  return pick
}
