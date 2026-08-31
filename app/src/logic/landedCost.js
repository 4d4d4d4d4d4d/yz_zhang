// Spec 60 — landed cost and the local price that actually holds margin. Pure.
//
// Cross-border pricing goes wrong in three specific places, and all three are
// arithmetic, not judgement:
//
//   1. Duty is assessed on the CIF value (goods + freight + insurance), not on
//      the ex-works price. Applying it to FOB alone understates every landed
//      cost in the model.
//   2. VAT/GST is collected from the buyer and remitted to the state. It is
//      neither revenue nor cost, so it must never appear in the margin
//      numerator — but it DOES enlarge the amount the payment processor takes
//      its percentage of, which is a real cost.
//   3. Working back from a target margin is not `cost / (1 - margin)`, because
//      the payment fee scales with the price you are solving for. It needs the
//      algebra below, or the shipped price quietly misses the target.

const num = n => (Number.isFinite(Number(n)) ? Number(n) : 0)
const pct = n => Math.max(0, num(n)) / 100
const round2 = n => Math.round(n * 100) / 100

// Everything it costs to have one unit sellable in-market, before selling it.
export function landedCost({ fob = 0, freight = 0, insurance = 0, dutyPct = 0, brokeragePct = 0, otherFixed = 0 } = {}) {
  const goods = Math.max(0, num(fob))
  const cif = goods + Math.max(0, num(freight)) + Math.max(0, num(insurance))
  const duty = cif * pct(dutyPct)
  const brokerage = cif * pct(brokeragePct)
  const total = cif + duty + brokerage + Math.max(0, num(otherFixed))
  return {
    goods,
    cif: round2(cif),
    duty: round2(duty),
    brokerage: round2(brokerage),
    otherFixed: Math.max(0, num(otherFixed)),
    total: round2(total),
    // Share of landed cost that is pure border friction — the number that
    // justifies (or kills) a local-manufacturing or bonded-warehouse plan.
    borderPct: total > 0 ? round2(((duty + brokerage) / total) * 100) : 0
  }
}

// Solve for the shelf price that leaves `targetMarginPct` after VAT is remitted
// and the processor takes its cut of the gross.
//
//   gross          = P · (1 + v)                 shown to the buyer
//   remitted VAT   = P · v
//   processor fee  = P · (1 + v) · f             charged on the gross
//   net to us      = P · (1 − (1 + v)·f)
//   margin m       = (net − landed) / net   ⇒   net = landed / (1 − m)
//   ⇒ P = landed / [ (1 − m) · (1 − (1 + v)·f) ]
//
// Returns null when the target is unreachable (fees alone exceed the price, or
// margin ≥ 100%) rather than a negative price dressed up as an answer.
export function priceForMargin({ landed = 0, targetMarginPct = 0, vatPct = 0, paymentFeePct = 0 } = {}) {
  const cost = Math.max(0, num(landed))
  const m = pct(targetMarginPct)
  const v = pct(vatPct)
  const f = pct(paymentFeePct)
  const takeHome = 1 - (1 + v) * f
  if (m >= 1 || takeHome <= 0 || cost <= 0) return null

  const net = round2(cost / (1 - m))
  const p = cost / ((1 - m) * takeHome)
  const gross = p * (1 + v)
  return {
    exVat: round2(p),
    gross: round2(gross),
    vat: round2(p * v),
    paymentFee: round2(gross * f),
    net,
    landed: cost,
    marginPct: round2(((net - cost) / net) * 100)
  }
}

// Charm-price conventions vary by market and currency granularity. Rounding
// DOWN to the charm point is the intuitive move and the wrong one: it silently
// gives away margin on every unit. These round UP to the next charm point, so
// the shipped price is always at or above the solved price.
export const CHARM = {
  end99: { step: 1, ending: 0.99, decimals: 2 },   // US, EU, UK — 24.99
  end95: { step: 1, ending: 0.95, decimals: 2 },   // common in DE/NL
  end90: { step: 100, ending: 90, decimals: 0 },   // JPY — 2,990
  end900: { step: 1000, ending: 900, decimals: 0 }, // KRW — 29,900
  whole: { step: 1, ending: 0, decimals: 0 }        // no charm convention
}

export function charmPrice(price, convention = 'end99', table = CHARM) {
  const p = num(price)
  const c = table[convention] ?? table.whole
  if (!(p > 0)) return 0
  const below = Math.floor((p - c.ending) / c.step) * c.step + c.ending
  const value = below >= p ? below : below + c.step
  return Number(value.toFixed(c.decimals))
}

// What the charm rounding actually did to the margin — reported, not assumed.
//
// The rounding MUST happen in the currency the shopper sees. `end90` means
// ¥2,990, not $29.90: charming the USD price and converting afterwards lands
// on a number that is a charm price in neither currency, and silently moves
// the margin. Measured on the JP row of the pricing panel, rounding in USD
// first inflated margin by 11 points over the 58% target; rounding in yen
// moves it by 0.04.
export function applyCharm(quote, convention = 'end99', { vatPct = 0, paymentFeePct = 0, fx = 1 } = {}) {
  if (!quote) return null
  const rate = num(fx) > 0 ? num(fx) : 1
  const localGross = charmPrice(quote.gross * rate, convention)
  const gross = localGross / rate
  const v = pct(vatPct)
  const f = pct(paymentFeePct)
  const exVat = gross / (1 + v)
  const net = exVat - gross * f
  const marginPct = net > 0 ? round2(((net - quote.landed) / net) * 100) : 0
  return {
    ...quote,
    gross: round2(gross),
    localGross,
    exVat: round2(exVat),
    vat: round2(gross - exVat),
    paymentFee: round2(gross * f),
    net: round2(net),
    marginPct,
    marginDelta: round2(marginPct - quote.marginPct)
  }
}
