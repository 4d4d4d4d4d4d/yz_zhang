// Spec 45 — A/B test statistical significance (two-proportion z-test), the
// core of any experimentation platform (Optimizely/VWO/Statsig). Pure and
// deterministic: no RNG, a closed-form normal CDF.

// Abramowitz & Stegun 7.1.26 erf approximation (|error| < 1.5e-7).
function erf(x) {
  const sign = x < 0 ? -1 : 1
  const ax = Math.abs(x)
  const t = 1 / (1 + 0.3275911 * ax)
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-ax * ax)
  return sign * y
}

export function normalCdf(z) {
  return 0.5 * (1 + erf(z / Math.SQRT2))
}

// convA/nA = control conversions/visitors; convB/nB = treatment. Returns the
// rates, absolute difference, relative lift, z-score, two-tailed p-value, a
// significance verdict at `alpha`, and a 95% CI on the difference.
export function proportionZTest({ convA, nA, convB, nB, alpha = 0.05 } = {}) {
  const a = Number(nA), b = Number(nB)
  if (!(a > 0) || !(b > 0)) return { valid: false }

  const rateA = Number(convA) / a
  const rateB = Number(convB) / b
  const pooled = (Number(convA) + Number(convB)) / (a + b)
  const sePooled = Math.sqrt(pooled * (1 - pooled) * (1 / a + 1 / b))
  const z = sePooled > 0 ? (rateB - rateA) / sePooled : 0
  const pValue = 2 * (1 - normalCdf(Math.abs(z)))
  const seDiff = Math.sqrt((rateA * (1 - rateA)) / a + (rateB * (1 - rateB)) / b)
  const diff = rateB - rateA

  return {
    valid: true,
    rateA, rateB, diff,
    lift: rateA > 0 ? diff / rateA : 0,
    z, pValue,
    significant: pValue < alpha,
    ci95: [diff - 1.96 * seDiff, diff + 1.96 * seDiff]
  }
}

// Operator-facing verdict: ship / keep testing / flat.
export function recommendation(result) {
  if (!result || !result.valid) return 'invalid'
  if (!result.significant) return 'keep_testing'
  return result.diff > 0 ? 'ship' : 'rollback'
}
