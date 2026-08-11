// Spec 04 — negotiation core: ZOPA, anchoring, playbook term evaluation.

export function zopa(buyer, seller) {
  const max = Number(buyer?.max), min = Number(seller?.min)
  if (!Number.isFinite(max) || !Number.isFinite(min) || max < min) {
    return { exists: false, low: null, high: null, width: 0, midpoint: null }
  }
  return { exists: true, low: min, high: max, width: max - min, midpoint: (max + min) / 2 }
}

// Spec 49 — discount-axis ZOPA. A higher discount favours the buyer, so the
// zone runs from the buyer's MINIMUM acceptable discount up to the seller's
// MAXIMUM tolerable discount. Both bounds are reservations (walk-away points);
// targets are aspirations and never define the zone. Delegates to zopa() so
// there is exactly one implementation of the overlap rule.
export function discountZopa(buyerMinDiscount, sellerMaxDiscount) {
  return zopa({ max: sellerMaxDiscount }, { min: buyerMinDiscount })
}

// Value capture: where a settlement lands inside the zone. On the discount
// axis a higher settlement favours the buyer. Settlements outside the zone are
// clamped to it — you cannot capture surplus that does not exist.
export function surplusSplit(zone, settlement) {
  if (!zone?.exists || !(zone.width > 0)) return null
  const s = Math.min(zone.high, Math.max(zone.low, Number(settlement) || 0))
  const buyerShare = (s - zone.low) / zone.width
  return { settlement: s, buyerShare, sellerShare: 1 - buyerShare }
}

// NOTE: framed in PRICE space — the seller favours the high end.
export function suggestAnchor(zone, side, aggressiveness = 0.7) {
  if (!zone?.exists) return null
  const a = Math.min(1, Math.max(0, aggressiveness))
  return side === 'seller'
    ? zone.high - (1 - a) * zone.width * 0.5
    : zone.low + (1 - a) * zone.width * 0.5
}

// Spec 49 — on the DISCOUNT axis the preferences invert: the seller favours
// the low end (small discount) and the buyer the high end. Mapping the flip
// here stops every caller from having to remember it.
export function discountAnchor(zone, side, aggressiveness = 0.7) {
  return suggestAnchor(zone, side === 'seller' ? 'buyer' : 'seller', aggressiveness)
}

// Evaluate a proposal against playbook rules.
// Rule: { term, op: 'max'|'min'|'oneOf'|'required', value, severity: 'block'|'warn', label? }
export function evaluateTerms(proposal = {}, playbook = { rules: [] }) {
  const findings = []
  const skipped = []
  for (const rule of playbook.rules || []) {
    if (!rule || !rule.term || !rule.op) { skipped.push(rule); continue }
    const severity = rule.severity === 'block' ? 'block' : 'warn'
    const actual = proposal[rule.term]
    const base = { term: rule.term, severity, label: rule.label || rule.term, actual }

    if (rule.op === 'required') {
      if (actual == null || actual === '') findings.push({ ...base, message: 'required term missing', suggestion: rule.value ?? null })
      continue
    }
    if (actual == null) continue // absent optional terms: not this rule's job

    if (rule.op === 'max') {
      if (Number(actual) > Number(rule.value)) findings.push({ ...base, message: `exceeds max ${rule.value}`, suggestion: rule.value })
    } else if (rule.op === 'min') {
      if (Number(actual) < Number(rule.value)) findings.push({ ...base, message: `below min ${rule.value}`, suggestion: rule.value })
    } else if (rule.op === 'oneOf') {
      const allowed = Array.isArray(rule.value) ? rule.value : []
      if (!allowed.includes(actual)) findings.push({ ...base, message: `must be one of ${allowed.join(', ')}`, suggestion: allowed[0] ?? null })
    } else {
      skipped.push(rule)
    }
  }
  const verdict = findings.some(f => f.severity === 'block') ? 'reject'
    : findings.length ? 'counter'
    : 'accept'
  return { verdict, findings, skipped }
}
