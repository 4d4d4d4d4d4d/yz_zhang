# Spec 43 — Availability SLA Service Credits

**Status:** Accepted · **Depends on:** 16 (customer success), 33 (format)

## 1. Problem (critical analysis)

`customerSuccess.js` models **support-ticket** SLAs (response time, breach), but
the platform sells to enterprises whose contracts hinge on an **availability
SLA with service credits** — the AWS/Twilio/Stripe schedule where uptime below
the committed level earns the customer a percentage of the monthly fee back.
That schedule was nowhere in the product, so the trust/support surface couldn't
answer the single question an enterprise buyer asks: "what do I get if you go
down?"

## 2. Scope

- `logic/slaCredit.js` — pure: `uptimeFromDowntime` (clamped, guarded),
  `serviceCredit(uptime, {commitment, schedule})` (0 when met; otherwise the
  highest tier whose floor the uptime clears), `creditAmount`, and `slaReport`
  bundling it for a billing period. `DEFAULT_SCHEDULE` = 99.0→10% / 95.0→25% /
  <95%→50%.
- `SupportSLA.vue` — an **Availability SLA** panel: current-period uptime vs
  commitment, the credit % + dollar amount owed (via `useFormat`), and the tier
  ladder with the active tier highlighted.

## 3. Review record

**R1 — meeting the commitment earns nothing.** `serviceCredit` returns 0 at or
above the commitment; credits only accrue on a genuine breach, matching how
real SLAs read.

**R2 — tiers by floor, largest credit first.** The schedule is evaluated
high-floor-first so an uptime lands in exactly one band; a custom schedule is
injectable, and an empty schedule yields 0 (never throws).

**R3 — fail safe on bad input.** No period, negative downtime, or non-numeric
fee resolve to full uptime / 0 credit rather than NaN on an invoice-facing number.

## 4. Tests
`tests/slaCredit.test.js`: uptime math + clamps/guards, tier boundaries
(met / 10 / 25 / 50), custom schedule, empty-schedule fallback, credit amount,
and the `slaReport` met/breached shapes. Panel rendering covered by mount-smoke.

## 5. Gate
`npm run test:coverage` (functions 100%), `npm run build`, `check:bundle` within
budget, plus a browser smoke: 65 min downtime over 30 days → 99.850% uptime,
10% credit, $1,200 owed, breached tier highlighted.
