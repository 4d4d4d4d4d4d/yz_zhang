// Spec 34 — deal readiness report. Turns a pipeline `dealReadiness` result
// into a shareable, printable structure: a headline verdict, per-stage status,
// severity-ordered blockers, and a timestamp. Pure and self-contained — it
// reads only the readiness shape (stages come from `credits`), so it imports
// no other domain module (spec 00 §2).

// A stage credit of 1 is complete, 0.5 partial, 0 open.
function statusOf(credit) {
  if (credit >= 1) return 'complete'
  if (credit >= 0.5) return 'partial'
  return 'open'
}

// Headline verdict: a hard-fail blocks regardless of score; otherwise ready
// only when the pipeline says so; else still in progress.
export function reportVerdict(readiness) {
  if (readiness?.hardFail) return 'blocked'
  return readiness?.readyToSign ? 'ready' : 'progress'
}

export function buildDealReport(readiness, { now = Date.now(), id = 'DEAL' } = {}) {
  const credits = readiness?.credits ?? {}
  const stages = Object.keys(credits).map(stage => ({
    stage,
    credit: credits[stage],
    status: statusOf(credits[stage])
  }))

  // Severity order: zero (hard) before half (soft), so the sharpest blocker
  // reads first on the one-pager. Stable within a severity band.
  const rank = { zero: 0, half: 1 }
  const blockers = [...(readiness?.blockers ?? [])].sort(
    (a, b) => (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9)
  )

  const complete = stages.filter(s => s.status === 'complete').length

  return {
    id,
    verdict: reportVerdict(readiness),
    score: readiness?.score ?? 0,
    stages,
    complete,
    total: stages.length,
    blockers,
    generatedAt: now
  }
}
