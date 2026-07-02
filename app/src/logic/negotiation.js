// Spec 04 — negotiation core: ZOPA, anchoring, playbook term evaluation.

export function zopa(buyer, seller) {
  const max = Number(buyer?.max), min = Number(seller?.min)
  if (!Number.isFinite(max) || !Number.isFinite(min) || max < min) {
    return { exists: false, low: null, high: null, width: 0, midpoint: null }
  }
  return { exists: true, low: min, high: max, width: max - min, midpoint: (max + min) / 2 }
}

export function suggestAnchor(zone, side, aggressiveness = 0.7) {
  if (!zone?.exists) return null
  const a = Math.min(1, Math.max(0, aggressiveness))
  return side === 'seller'
    ? zone.high - (1 - a) * zone.width * 0.5
    : zone.low + (1 - a) * zone.width * 0.5
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
