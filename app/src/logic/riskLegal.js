// Spec 05 — risk & legal: market regime rules, campaign gate, due diligence.

export const MARKET_REGIMES = {
  US: ['CCPA', 'FTC'],
  EU: ['GDPR', 'DSA'],
  UK: ['UKGDPR'],
  JP: ['APPI'],
  KR: ['PIPA'],
  CN: ['PIPL'],
  BR: ['LGPD'],
  SG: ['PDPA']
}

export const REGIME_REQUIREMENTS = {
  GDPR: ['consent', 'dpa', 'localization'],
  UKGDPR: ['consent', 'dpa'],
  CCPA: ['consent', 'adDisclosure'],
  FTC: ['adDisclosure', 'provenance'],
  DSA: ['adDisclosure', 'ageGate', 'provenance'],
  APPI: ['consent', 'localization'],
  PIPA: ['consent', 'localization'],
  PIPL: ['consent', 'dpa', 'localization'],
  LGPD: ['consent', 'dpa'],
  PDPA: ['consent']
}

const SEVERITY = {
  consent: 'block',
  dpa: 'block',
  localization: 'warn',
  ageGate: 'warn',
  adDisclosure: 'warn',
  provenance: 'warn'
}

const SCORE = { block: 25, warn: 10 }

function toResult(findings) {
  const riskScore = Math.min(100, findings.reduce((s, f) => s + SCORE[f.severity], 0))
  const gate = findings.some(f => f.severity === 'block') ? 'block'
    : findings.length ? 'review'
    : 'pass'
  return { riskScore, gate, findings }
}

export function assessCampaign(campaign = {}) {
  const markets = campaign.markets || []
  const attrs = campaign.attributes || {}
  const findings = []
  const required = new Map() // requirement -> markets demanding it (deduped)

  for (const market of markets) {
    const regimes = MARKET_REGIMES[market]
    if (!regimes) {
      // Fail closed: unknown markets surface, never silently pass.
      findings.push({ key: 'unknown-market', market, severity: 'warn', message: `no rule coverage for market ${market} — needs manual review` })
      continue
    }
    for (const regime of regimes) {
      for (const req of REGIME_REQUIREMENTS[regime] || []) {
        if (!required.has(req)) required.set(req, [])
        required.get(req).push(`${market}/${regime}`)
      }
    }
  }

  for (const [req, sources] of required) {
    if (!attrs[req]) {
      findings.push({ key: req, severity: SEVERITY[req] || 'warn', message: `unmet requirement "${req}"`, sources: [...new Set(sources)] })
    }
  }
  return toResult(findings)
}

const DILIGENCE_CHECKS = [
  { key: 'kyb', severity: 'block', message: 'KYB (business verification) incomplete' },
  { key: 'sanctions', severity: 'block', message: 'sanctions screening not run' },
  { key: 'references', severity: 'warn', message: 'no verified references' },
  { key: 'financials', severity: 'warn', message: 'financial health unverified' },
  { key: 'dataProcessing', severity: 'warn', message: 'data-processing terms unsigned' }
]

export function dueDiligence(partner = {}) {
  const checks = partner.checks || {}
  const findings = DILIGENCE_CHECKS
    .filter(c => !checks[c.key])
    .map(c => ({ key: c.key, severity: c.severity, message: c.message }))
  return toResult(findings)
}
