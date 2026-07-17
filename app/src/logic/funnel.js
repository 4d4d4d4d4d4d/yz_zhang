// Spec 30 — funnel analysis over the recorder's event stream. Pure,
// total, div-by-zero safe.

// events: [{ name }]. stages: ordered event names defining the funnel.
export function analyzeFunnel(events = [], stages = []) {
  const counts = new Map(stages.map(s => [s, 0]))
  for (const e of events) {
    if (counts.has(e.name)) counts.set(e.name, counts.get(e.name) + 1)
  }

  const steps = stages.map((stage, i) => {
    const count = counts.get(stage)
    if (i === 0) return { stage, count, rate: 1 }
    const prev = counts.get(stages[i - 1])
    const rate = prev > 0 ? count / prev : 0 // never NaN
    return { stage, count, rate }
  })

  const first = steps[0]?.count ?? 0
  const last = steps[steps.length - 1]?.count ?? 0
  const overall = first > 0 ? last / first : 0

  // Biggest drop: the transition (step ≥ 1) with the lowest retention.
  let biggestDrop = null
  for (let i = 1; i < steps.length; i++) {
    if (!biggestDrop || steps[i].rate < biggestDrop.rate) {
      biggestDrop = { stage: steps[i].stage, from: stages[i - 1], rate: steps[i].rate }
    }
  }

  return { steps, overall, biggestDrop }
}
