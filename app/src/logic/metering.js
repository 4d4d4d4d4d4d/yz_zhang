// Spec 15 — usage metering: overage premium + invoice + pace projection.

// Overage premium applies only past the included allowance:
// 40% premium on the pro-rata share of the meter's cost.
export function meterBill(meter) {
  const { used = 0, included = 0, cost = 0 } = meter
  const utilization = included > 0 ? used / included : 0
  const overage = used > included && included > 0
    ? Math.round(cost * ((used - included) / included) * 0.4)
    : 0
  return { utilization, cost, overage }
}

// Invoice total includes the overage premium (spec 15 R1: the inline
// component computed overage but left it out of the total).
export function invoice(baseFee, meters = []) {
  const bills = meters.map(meterBill)
  const usage = bills.reduce((s, b) => s + b.cost, 0)
  const overage = bills.reduce((s, b) => s + b.overage, 0)
  return { base: baseFee, usage, overage, total: baseFee + usage + overage, bills }
}

// Linear projection: usage-driven parts scale with the month, base is flat.
export function projectedTotal(inv, dayOfMonth, daysInMonth) {
  if (!dayOfMonth || dayOfMonth <= 0) return inv.base
  const factor = daysInMonth / dayOfMonth
  return inv.base + (inv.usage + inv.overage) * factor
}
