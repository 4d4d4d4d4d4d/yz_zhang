// Spec 15 — CPQ: quote pricing + approval escalation matrix.

export function priceQuote(lines = [], catalog = []) {
  const bySku = new Map(catalog.map(p => [p.id, p]))
  const priced = []
  const skipped = []
  for (const l of lines) {
    const p = bySku.get(l.sku)
    if (!p) { skipped.push(l.sku); continue }
    const qty = Math.max(0, Number(l.qty) || 0)
    const discount = Math.min(100, Math.max(0, Number(l.discount) || 0))
    const gross = p.list * qty
    const disc = gross * discount / 100
    const net = gross - disc
    const cost = p.cost * qty
    const margin = net > 0 ? ((net - cost) / net) * 100 : 0
    priced.push({ sku: l.sku, qty, discount, product: p, gross, disc, net, cost, margin })
  }
  const totals = {
    net: priced.reduce((s, l) => s + l.net, 0),
    discount: priced.reduce((s, l) => s + l.disc, 0),
    cost: priced.reduce((s, l) => s + l.cost, 0)
  }
  totals.gross = totals.net + totals.discount
  totals.blendedDiscount = totals.gross > 0 ? (totals.discount / totals.gross) * 100 : 0
  totals.blendedMargin = totals.net > 0 ? ((totals.net - totals.cost) / totals.net) * 100 : 0
  return { lines: priced, skipped, totals }
}

// Escalation matrix. `to` is the inclusive upper bound of a tier; the last tier
// is open-ended. The console draws its approval bar from this same table, so a
// threshold change moves routing, copy and geometry together instead of leaving
// the bar quietly disagreeing with the routing it illustrates.
export const APPROVAL_TIERS = [
  { key: 'auto', to: 5, color: 'ok' },
  { key: 'manager', to: 15, color: 'warn' },
  { key: 'vp', to: 25, color: 'risk' },
  { key: 'exec', to: Infinity, color: 'risk' }
]

// Returns a tier key, not display copy — the label is the view's business, and
// a logic layer that emits English cannot be translated.
export function approvalFor(blendedDiscount, tiers = APPROVAL_TIERS) {
  const d = Number(blendedDiscount) || 0
  const index = Math.max(0, tiers.findIndex(t => d <= t.to))
  return { ...tiers[index], index }
}

// The bar draws each tier as an equal-width column, but the tiers span unequal
// discount ranges (0-5, 5-15, 15-25, 25+). A linear scale therefore lands the
// marker in the wrong column: at 8% blended discount it sat inside the "Auto"
// band while the routing beside it read "Sales Manager". Map piecewise so the
// marker is always inside the tier that is actually going to approve.
export function markerPercent(blendedDiscount, tiers = APPROVAL_TIERS) {
  const d = Math.max(0, Number(blendedDiscount) || 0)
  const width = 100 / tiers.length
  const { index } = approvalFor(d, tiers)
  const from = index === 0 ? 0 : tiers[index - 1].to
  const to = tiers[index].to
  // Open-ended top tier: give it one tier-width of headroom before saturating.
  const span = Number.isFinite(to) ? to - from : from
  const frac = span > 0 ? Math.min(1, (d - from) / span) : 1
  return index * width + frac * width
}

// How much net must be added to lift blended margin to `floorPct`?
// margin = (net - cost) / net, and trimming a discount raises net while leaving
// cost untouched, so the required delta is the same whichever line supplies it:
//   (N + d - C) / (N + d) = f  =>  N + d = C / (1 - f)
// What differs per line is whether it has the discount headroom to supply it.
export function marginRecovery(quote, floorPct = 50, step = 0.1) {
  const { net: N, cost: C } = quote?.totals ?? {}
  const f = Math.min(99.9, Math.max(0, Number(floorPct) || 0)) / 100
  if (!(N > 0)) return null
  const marginNow = ((N - C) / N) * 100
  const needed = C / (1 - f) - N
  if (!(needed > 0)) return null // already at or above the floor

  // Prefer trimming the deepest discount: it is the least defensible one, and
  // every feasible line costs the buyer exactly the same `needed` dollars.
  const candidates = (quote.lines ?? [])
    .filter(l => l.discount > 0 && l.gross > 0)
    .sort((a, b) => b.discount - a.discount || b.gross - a.gross)

  const pick = candidates.find(l => l.gross * (l.discount / 100) >= needed)
  if (!pick) {
    const headroom = candidates.reduce((s, l) => s + l.gross * (l.discount / 100), 0)
    return { feasible: false, marginNow, floor: floorPct, needed, headroom }
  }

  // Round the recommended discount DOWN to the step so the rep typing it in
  // lands at or above the floor, never a hair under it.
  const exact = pick.discount - (needed / pick.gross) * 100
  const toDiscount = Math.max(0, Math.floor(exact / step) * step)
  const added = pick.gross * ((pick.discount - toDiscount) / 100)
  const after = ((N + added - C) / (N + added)) * 100
  return {
    feasible: true,
    needed,
    sku: pick.sku,
    product: pick.product?.name ?? pick.sku,
    fromDiscount: pick.discount,
    toDiscount,
    added,
    marginNow,
    marginAfter: after,
    floor: floorPct
  }
}
