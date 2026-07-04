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

// Escalation matrix — boundary values belong to the lower tier.
export function approvalFor(blendedDiscount) {
  const d = Number(blendedDiscount) || 0
  if (d <= 5) return { level: 'Auto-approved', who: 'Self-serve', color: 'ok' }
  if (d <= 15) return { level: 'Sales Manager', who: "AM's manager", color: 'warn' }
  if (d <= 25) return { level: 'VP Sales', who: 'CRO', color: 'risk' }
  return { level: 'CFO + CEO', who: 'Exec committee', color: 'risk' }
}
