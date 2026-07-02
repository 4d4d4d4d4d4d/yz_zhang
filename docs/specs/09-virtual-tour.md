# Spec 09 — Virtual Factory Tour (模拟厂房参观 · VR 式在线漫游)

Status: **Approved** · Review: R1 (2026-07-02) · Domain: `logic/tour.js`

## Problem

"Come see the factory" doesn't scale across borders. A field team
captures the site once (3D/360° footage, offline); buyers then walk the
plant online — VR-style station-to-station navigation with verified
capture metadata. The tour is itself trust evidence: capture date,
operator, and provenance hash chain into spec 06's showcase layer.

## Design

### Tour graph
A tour is a directed graph of stations:
`{ id, name, zone, pano, captured, hotspots: [{ to, label }] }`.
Edges are physical walkways — navigation follows real plant topology,
not teleportation (review decision: spatial continuity is what makes it
feel like a visit).

### `validateTour(tour)`
- Every hotspot target must exist; every station reachable from the
  entrance; duplicate ids rejected. Returns `{ ok, problems[] }` —
  content ops run this before publishing a capture.

### `shortestPath(tour, from, to)`
- BFS hop-count path (guides "take me to QA lab"). Unreachable → `null`.

### `coverage(visited, tour)`
- % of stations visited, per-zone breakdown, and `missed[]` — the
  operator's cue ("you haven't shown them the clean room").

### `pickRendition(bandwidthMbps, renditions)`
- Adaptive quality: highest rendition whose `minMbps` fits, else the
  lowest as floor (a tour must never hard-fail on a slow link).
  Deterministic, monotonic in bandwidth.

## Test plan
- validateTour catches dangling hotspot, unreachable station, dup ids.
- BFS: known fixture shortest hops; null when unreachable.
- Coverage: partial visit %, zone breakdown, missed list.
- Rendition: exact thresholds, floor behavior at 0 Mbps, monotonicity.

## Review record — R1
- ✅ Walkway-graph navigation over free teleport (spatial trust).
- ✅ Rendition floor: degrade, never deny (overseas links vary wildly).
- Verdict: **approved**.
