// Spec 60 — retail moments and backward lead-time planning. Pure; `now` injected.
//
// Every market has dates you cannot move: Singles' Day, Black Friday, Golden
// Week, Ramadan, El Buen Fin. Missing one costs a year. Planning forward from
// today is how they get missed; the only correct direction is backward from
// the immovable date, through each stage's duration, to the latest possible
// start. If that start is already behind you, the campaign is late TODAY —
// which is exactly the thing a calendar of coloured pills never tells you.

const DAY = 86400000
const num = n => (Number.isFinite(Number(n)) ? Number(n) : 0)

// Default production pipeline for a localized video campaign, in days.
// Ordered as executed; the backward pass walks it in reverse.
export const STAGES = [
  { key: 'brief', days: 5 },
  { key: 'render', days: 7 },   // AI render + brand review
  { key: 'localize', days: 6 }, // voice, subtitles, cultural QA per market
  { key: 'legal', days: 4 },    // claims review in-market
  { key: 'traffic', days: 3 }   // media buy lock, creative trafficking
]

export function leadTimeDays(stages = STAGES) {
  return (Array.isArray(stages) ? stages : []).reduce((s, st) => s + Math.max(0, num(st?.days)), 0)
}

// Backward pass from the moment's date. Returns stages in execution order,
// each with the latest start/end that still lands on time.
export function backwardPlan(momentAt, now = Date.now(), stages = STAGES) {
  const target = num(momentAt)
  const list = Array.isArray(stages) ? stages : []
  const out = []
  let cursor = target
  for (let i = list.length - 1; i >= 0; i--) {
    const days = Math.max(0, num(list[i]?.days))
    const end = cursor
    const start = cursor - days * DAY
    out.unshift({ key: list[i]?.key, days, start, end, late: start < now })
    cursor = start
  }
  const startBy = cursor
  const slackDays = Math.floor((startBy - now) / DAY)
  return {
    momentAt: target,
    startBy,
    leadDays: leadTimeDays(list),
    slackDays,
    // Three honest states, not two: on track, late to start but the date is
    // still reachable by compressing, and past the date entirely.
    status: target < now ? 'passed' : slackDays < 0 ? 'late' : 'ontrack',
    stages: out
  }
}

// Moments still ahead, soonest first, each with its plan. `horizonDays` keeps
// the panel to a planning window instead of a year of noise.
export function upcomingMoments(moments = [], now = Date.now(), { horizonDays = 240, stages = STAGES } = {}) {
  const limit = now + Math.max(0, num(horizonDays)) * DAY
  return (Array.isArray(moments) ? moments : [])
    .filter(m => num(m?.at) >= now && num(m?.at) <= limit)
    .sort((a, b) => num(a.at) - num(b.at))
    .map(m => ({ ...m, plan: backwardPlan(m.at, now, stages) }))
}

// Moments whose start date has already passed — the actionable subset, and the
// reason this panel exists rather than a calendar widget.
export function atRisk(moments = [], now = Date.now(), opts = {}) {
  return upcomingMoments(moments, now, opts).filter(m => m.plan.status === 'late')
}
