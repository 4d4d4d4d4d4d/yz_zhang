// Spec 44 — cross-border quote conversion. Pure. Converts a USD contract value
// to a partner's currency at an INJECTED rate (the component supplies the rate
// from the pricing table, so this stays dependency-free per spec 00 §2). Large
// B2B contract values are quoted in whole currency units, no cents.

export function convertAmount(usd, rate) {
  return Math.round((Number(usd) || 0) * (Number(rate) || 0))
}

// Build the partner-currency view of a USD net TCV. `isUsd` lets the UI skip
// the FX disclaimer when no conversion happened.
export function crossBorderQuote(netUsd, { code = 'USD', rate = 1 } = {}) {
  return {
    code,
    rate: Number(rate) || 0,
    netUsd: Math.round(Number(netUsd) || 0),
    net: convertAmount(netUsd, rate),
    isUsd: code === 'USD'
  }
}
