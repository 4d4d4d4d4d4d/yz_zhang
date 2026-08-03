// Spec 43 — availability SLA service credits (AWS/Twilio/Stripe-style). Pure.
// A monthly uptime below the committed level earns the customer a service
// credit — a percentage of the monthly fee, tiered by how far short it fell.

// Lower uptime → larger credit. Each tier is the floor it applies from.
export const DEFAULT_SCHEDULE = [
  { minUptime: 99.0, credit: 10 }, // [99.0, commitment)
  { minUptime: 95.0, credit: 25 }, // [95.0, 99.0)
  { minUptime: 0,    credit: 50 }  // < 95.0
]

const clampPct = n => Math.min(100, Math.max(0, Number(n) || 0))

// Monthly uptime % from observed downtime over the billing period.
export function uptimeFromDowntime(downtimeMinutes, periodMinutes) {
  if (!(periodMinutes > 0)) return 100
  const up = (1 - (Math.max(0, Number(downtimeMinutes) || 0) / periodMinutes)) * 100
  return clampPct(up)
}

// Credit % owed for an uptime against a commitment. Meeting the commitment
// earns nothing; otherwise the highest tier whose floor the uptime clears.
export function serviceCredit(uptimePct, { commitment = 99.9, schedule = DEFAULT_SCHEDULE } = {}) {
  if (uptimePct >= commitment) return 0
  const sorted = [...schedule].sort((a, b) => b.minUptime - a.minUptime)
  for (const tier of sorted) {
    if (uptimePct >= tier.minUptime) return tier.credit
  }
  return sorted.length ? sorted[sorted.length - 1].credit : 0
}

export function creditAmount(monthlyFee, creditPct) {
  return Math.round(((Number(monthlyFee) || 0) * (Number(creditPct) || 0)) / 100)
}

// One report for a billing period.
export function slaReport({ uptimePct, commitment = 99.9, monthlyFee = 0, schedule = DEFAULT_SCHEDULE } = {}) {
  const up = clampPct(uptimePct)
  const creditPct = serviceCredit(up, { commitment, schedule })
  return {
    uptimePct: up,
    commitment,
    met: up >= commitment,
    creditPct,
    creditAmount: creditAmount(monthlyFee, creditPct)
  }
}
