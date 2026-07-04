// Spec 15 — revenue recognition schedules (ratable / point-in-time / milestone).

export function buildSchedule(contract, months = contract?.term ?? 12) {
  const obligations = contract?.obligations ?? []
  const rows = Array.from({ length: months }, (_, i) => ({ month: i + 1, obligations: {} }))

  for (const o of obligations) {
    for (let m = 0; m < months; m++) {
      let val = 0
      if (o.kind === 'ratable') {
        if (m >= o.start && m < o.end) val = o.amount / (o.end - o.start)
      } else if (o.kind === 'point-in-time') {
        if (m === o.start) val = o.amount
      } else if (o.kind === 'milestone') {
        const step = (o.end - o.start) / 3
        for (let i = 0; i < 3; i++) {
          if (Math.floor(o.start + step * i) === m) val += o.amount / 3
        }
      }
      rows[m].obligations[o.name] = val
    }
  }

  const monthlyTotals = rows.map(r => Object.values(r.obligations).reduce((s, v) => s + v, 0))
  let acc = 0
  const cumulative = monthlyTotals.map(v => (acc += v))
  const recognized = acc
  const deferred = (contract?.tcv ?? 0) - recognized
  return { rows, monthlyTotals, cumulative, recognized, deferred }
}
