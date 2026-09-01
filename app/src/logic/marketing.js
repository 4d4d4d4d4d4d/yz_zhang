// Spec 02 — budget allocation (ROAS-proportional water-fill) + pacing.

const toCents = v => Math.round(v * 100)
const fromCents = v => v / 100

// Allocate `total` across channels proportionally to ROAS, honoring
// min/max bounds. Water-fill: channels frozen at max release residue to
// the rest. Cent-exact via largest-remainder rounding.
export function allocateBudget(total, channels) {
  if (!Array.isArray(channels) || channels.length === 0) {
    return { allocations: {}, expectedReturn: 0 }
  }
  const totalC = toCents(total)
  const chans = channels.map(c => ({
    id: c.id,
    roas: Math.max(0, Number(c.roas) || 0),
    minC: toCents(c.min ?? 0),
    maxC: c.max == null ? Infinity : toCents(c.max)
  }))
  const sumMin = chans.reduce((s, c) => s + c.minC, 0)
  if (sumMin > totalC) {
    throw new Error(`sum of channel minimums (${fromCents(sumMin)}) exceeds total budget (${total})`)
  }

  const alloc = new Map(chans.map(c => [c.id, c.minC]))
  let remainder = totalC - sumMin
  let open = chans.filter(c => alloc.get(c.id) < c.maxC)

  while (remainder > 0 && open.length) {
    const sumRoas = open.reduce((s, c) => s + c.roas, 0)
    // No signal left: split remainder evenly among open channels.
    const shares = open.map(c => ({
      c,
      exact: sumRoas > 0 ? remainder * (c.roas / sumRoas) : remainder / open.length
    }))
    // Cap each share at channel headroom, floor to cents.
    let distributed = 0
    const capped = shares.map(({ c, exact }) => {
      const headroom = c.maxC - alloc.get(c.id)
      const grant = Math.min(Math.floor(exact), headroom)
      distributed += grant
      return { c, grant, frac: exact - Math.floor(exact), headroom: headroom - grant }
    })
    // Largest-remainder: hand out leftover cents to open headroom.
    let leftover = remainder - distributed
    capped.sort((a, b) => b.frac - a.frac)
    for (const item of capped) {
      if (leftover <= 0) break
      if (item.headroom > 0) { item.grant += 1; item.headroom -= 1; leftover -= 1 }
    }
    for (const { c, grant } of capped) alloc.set(c.id, alloc.get(c.id) + grant)
    const newRemainder = leftover
    const nextOpen = chans.filter(c => alloc.get(c.id) < c.maxC)
    // Guard: if nothing moved and nothing can, stop (all channels capped).
    if (newRemainder === remainder && nextOpen.length === open.length) break
    remainder = newRemainder
    open = nextOpen
  }

  const allocations = {}
  let expectedReturn = 0
  for (const c of chans) {
    const amt = fromCents(alloc.get(c.id))
    allocations[c.id] = amt
    expectedReturn += amt * c.roas
  }
  return { allocations, expectedReturn: Math.round(expectedReturn * 100) / 100, unallocated: fromCents(remainder) }
}

// Spec 51 — roll campaigns up to channels so the allocator has something to
// allocate across. Channel ROAS is SPEND-WEIGHTED (total revenue ÷ total
// spend), never a mean of per-campaign ROAS: averaging ratios lets a tiny
// high-ROAS campaign outvote the spend that actually carries the channel.
export function channelRollup(campaigns) {
  const byChannel = new Map()
  for (const c of Array.isArray(campaigns) ? campaigns : []) {
    const id = c?.channel
    if (!id) continue
    const cur = byChannel.get(id) || { id, spend: 0, revenue: 0, campaigns: 0 }
    const spend = Number(c.spend) || 0
    cur.spend += spend
    cur.revenue += spend * (Number(c.roas) || 0)
    cur.campaigns += 1
    byChannel.set(id, cur)
  }
  return [...byChannel.values()]
    .map(c => ({ ...c, roas: c.spend > 0 ? c.revenue / c.spend : 0 }))
    .sort((a, b) => b.spend - a.spend || a.id.localeCompare(b.id))
}

// Spec 51 — whole-percent shares that sum to exactly 100. Rounding each share
// independently can total 99 or 101, which then corrupts any consumer that
// assumes 100 (the budget reallocator does). Largest-remainder fixes the drift.
export function percentShares(amounts) {
  const entries = Object.entries(amounts || {})
  const total = entries.reduce((s, [, v]) => s + (Number(v) || 0), 0)
  if (!(total > 0)) return Object.fromEntries(entries.map(([k]) => [k, 0]))
  const exact = entries.map(([k, v]) => {
    const pct = ((Number(v) || 0) / total) * 100
    return { k, floor: Math.floor(pct), frac: pct - Math.floor(pct) }
  })
  let leftover = 100 - exact.reduce((s, e) => s + e.floor, 0)
  exact.sort((a, b) => b.frac - a.frac || a.k.localeCompare(b.k))
  for (const e of exact) {
    if (leftover <= 0) break
    e.floor += 1
    leftover -= 1
  }
  return Object.fromEntries(exact.map(e => [e.k, e.floor]))
}

// Linear pacing with ±10% tolerance band.
export function pacingStatus(budget, spent, elapsedDays, totalDays) {
  if (!totalDays || totalDays <= 0 || elapsedDays <= 0) {
    return { target: 0, delta: spent, status: 'on-track', dailyRunRate: 0, projectedTotal: spent }
  }
  const days = Math.min(elapsedDays, totalDays)
  const target = budget * (days / totalDays)
  const delta = spent - target
  const band = budget * 0.10
  const status = delta > band ? 'over' : delta < -band ? 'under' : 'on-track'
  const dailyRunRate = spent / days
  const projectedTotal = dailyRunRate * totalDays
  return { target, delta, status, dailyRunRate, projectedTotal }
}
