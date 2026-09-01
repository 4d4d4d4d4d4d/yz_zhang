// Spec 27 — single source of demo truth. Data only: no logic, no engine
// imports (fixtures are to entities what the registry is to structure).
// Modules that consume these entities import them instead of redeclaring.

export const ACCOUNTS = [
  { name: 'Lumen Studios',      mrr: 9800,  csm: 'Akiko', plan: 'Enterprise', signals: { usage: 92, payment: 100, support: 88, adoption: 84, sentiment: 92 }, renewalIn: 172, trend: 'up' },
  { name: 'Northwave Partners', mrr: 12400, csm: 'Akiko', plan: 'Enterprise', signals: { usage: 74, payment: 100, support: 82, adoption: 68, sentiment: 78 }, renewalIn: 68,  trend: 'flat' },
  { name: 'Aurora Media',       mrr: 6200,  csm: 'Kenji', plan: 'Enterprise', signals: { usage: 88, payment: 92,  support: 84, adoption: 76, sentiment: 84 }, renewalIn: 240, trend: 'up' },
  { name: 'Kaito Beauty',       mrr: 2400,  csm: 'Hana',  plan: 'Growth',     signals: { usage: 96, payment: 100, support: 76, adoption: 82, sentiment: 88 }, renewalIn: 316, trend: 'up' },
  { name: 'Cobalt Legal',       mrr: 1800,  csm: 'Diego', plan: 'Growth',     signals: { usage: 62, payment: 100, support: 72, adoption: 58, sentiment: 62 }, renewalIn: 124, trend: 'down' },
  { name: 'Mizu Logistics',     mrr:  980,  csm: 'Hana',  plan: 'Starter',    signals: { usage: 38, payment: 68,  support: 52, adoption: 34, sentiment: 42 }, renewalIn: 42,  trend: 'down' },
  { name: 'Helio Network',      mrr:  420,  csm: 'Diego', plan: 'Starter',    signals: { usage: 54, payment: 100, support: 68, adoption: 48, sentiment: 62 }, renewalIn: 220, trend: 'flat' },
  { name: 'Verda Commerce',     mrr:  380,  csm: 'Hana',  plan: 'Starter',    signals: { usage: 82, payment: 100, support: 92, adoption: 76, sentiment: 84 }, renewalIn: 96,  trend: 'up' }
]

// Tickets carry hour OFFSETS; materialize against an injected now so
// time stays testable (spec 13 rule 2 applied to fixtures).
const TICKETS = [
  { id: 'T-8241', title: 'Render queue stuck · JP region',       account: 'Lumen Studios',  sev: 'SEV1', assignee: 'On-call', dueInHours: -0.5, status: 'active',   sla: 1,  age: '3h 24m', csat: null },
  { id: 'T-8240', title: 'API returning 429 on burst',           account: 'Aurora Media',   sev: 'SEV2', assignee: 'Priya',   dueInHours: 4.2,  status: 'active',   sla: 8,  age: '5h 12m', csat: null },
  { id: 'T-8239', title: 'How to enable multi-market rendering', account: 'Kaito Beauty',   sev: 'SEV3', assignee: 'Marcus',  dueInHours: 38,   status: 'active',   sla: 48, age: '10h',    csat: null },
  { id: 'T-8238', title: 'SSO SAML metadata rotation',           account: 'Cobalt Legal',   sev: 'SEV2', assignee: 'Priya',   dueInHours: -2,   status: 'active',   sla: 8,  age: '11h',    csat: null },
  { id: 'T-8237', title: 'Invoice charge dispute · overage',     account: 'Mizu Logistics', sev: 'SEV3', assignee: 'Sofia',   dueInHours: 52,   status: 'active',   sla: 48, age: '4h',     csat: null },
  { id: 'T-8236', title: 'Bulk export missing 6 renders',        account: 'Northwave Partners', sev: 'SEV2', assignee: 'Marcus', dueInHours: 6, status: 'resolved', sla: 8,  age: '2d',    csat: 5 },
  { id: 'T-8235', title: 'Onboarding walkthrough scheduling',    account: 'Verda Commerce', sev: 'SEV3', assignee: 'Sofia',   dueInHours: 72,   status: 'resolved', sla: 48, age: '2d',     csat: 5 },
  { id: 'T-8234', title: 'Brand kit sync failed',                account: 'Lumen Studios',  sev: 'SEV2', assignee: 'Priya',   dueInHours: 6,    status: 'resolved', sla: 8,  age: '2d',     csat: 4 }
]

export function ticketsAt(now) {
  return TICKETS.map(({ dueInHours, ...t }) => ({
    ...t,
    due: new Date(now + dueInHours * 3600000).toISOString()
  }))
}

export const TENANTS = [
  { id: 'lumi',   name: 'Lumi DTC',       plan: 'Enterprise', mrr: 9800 },
  { id: 'kaito',  name: 'Kaito Beauty',   plan: 'Growth',     mrr: 2400 },
  { id: 'aurora', name: 'Aurora Media',   plan: 'Enterprise', mrr: 6200 },
  { id: 'verda',  name: 'Verda Commerce', plan: 'Starter',    mrr: 0 }
]

export const PLAN_BASE_FEES = { Enterprise: 5000, Growth: 999, Starter: 0 }

export const METERS = {
  lumi: [
    { k: 'API calls',   used: 2840000, included: 3000000, unit: 'req', rate: '$0.0008 / 1K', cost: 2272 },
    { k: 'GPU seconds', used: 184000,  included: 200000,  unit: 's',   rate: '$0.024 / s',   cost: 4416 },
    { k: 'Renders',     used: 12480,   included: 10000,   unit: 'job', rate: '$0.18 / job',  cost: 2246 },
    { k: 'Storage',     used: 4.2,     included: 5,       unit: 'TB',  rate: '$28 / TB-mo',  cost: 118 }
  ],
  kaito: [
    { k: 'API calls',   used: 460000, included: 500000, unit: 'req', rate: '$0.0012 / 1K', cost: 552 },
    { k: 'GPU seconds', used: 38000,  included: 40000,  unit: 's',   rate: '$0.026 / s',   cost: 988 },
    { k: 'Renders',     used: 1840,   included: 2000,   unit: 'job', rate: '$0.22 / job',  cost: 405 },
    { k: 'Storage',     used: 0.8,    included: 1,      unit: 'TB',  rate: '$32 / TB-mo',  cost: 26 }
  ],
  aurora: [
    { k: 'API calls',   used: 1680000, included: 2000000, unit: 'req', rate: '$0.0009 / 1K', cost: 1512 },
    { k: 'GPU seconds', used: 128000,  included: 150000,  unit: 's',   rate: '$0.025 / s',   cost: 3200 },
    { k: 'Renders',     used: 7820,    included: 8000,    unit: 'job', rate: '$0.20 / job',  cost: 1564 },
    { k: 'Storage',     used: 2.4,     included: 3,       unit: 'TB',  rate: '$30 / TB-mo',  cost: 72 }
  ],
  verda: [
    { k: 'API calls',   used: 28000, included: 50000, unit: 'req', rate: '$0.0015 / 1K', cost: 42 },
    { k: 'GPU seconds', used: 1800,  included: 2000,  unit: 's',   rate: '$0.030 / s',   cost: 54 },
    { k: 'Renders',     used: 142,   included: 200,   unit: 'job', rate: '$0.25 / job',  cost: 36 },
    { k: 'Storage',     used: 0.04,  included: 0.1,   unit: 'TB',  rate: '$40 / TB-mo',  cost: 2 }
  ]
}

// Compliance posture of the flagship campaign (one warn-level gap: ageGate).
export const CAMPAIGN = {
  markets: ['JP', 'EU'],
  attributes: { consent: true, dpa: true, localization: true, adDisclosure: true, provenance: true }
}

// Deal-readiness inputs for the active flagship deal (terms still in counter).
export const DEAL = {
  reelEvidence: { provenance: true, complianceGate: true },
  fieldCase: { state: 'evidence-collected', chainValid: true },
  compliance: { gate: 'pass' },
  diligence: { gate: 'pass' },
  terms: { verdict: 'counter' }
}
