// Spec 26 — notification center: pure alert derivation from real domain
// outputs (spec-19 composition pattern) + a deduping inbox with
// unread-safe eviction. The engine emits i18n keys, never strings.

export function deriveAlerts({ sla, health, compliance, invoice, readiness } = {}) {
  const alerts = []

  if (sla && sla.breached > 0) {
    alerts.push({
      key: 'sla-breach',
      severity: 'critical',
      msgKey: 'notify.msg.sla',
      params: { count: sla.breached },
      route: { name: 'console', params: { tab: 'trust' }, query: { sub: 'support' } }
    })
  }

  if (health && health.risk > 0) {
    alerts.push({
      key: 'churn-risk',
      severity: 'warning',
      msgKey: 'notify.msg.churn',
      params: { count: health.risk, mrr: health.mrrAtRisk },
      route: { name: 'console', params: { tab: 'trust' }, query: { sub: 'health' } }
    })
  }

  if (compliance && compliance.gate !== 'pass') {
    alerts.push({
      key: 'compliance-gate',
      severity: compliance.gate === 'block' ? 'critical' : 'warning',
      msgKey: 'notify.msg.compliance',
      params: { findings: compliance.findings?.length ?? 0 },
      route: { name: 'console', params: { tab: 'trust' }, query: { sub: 'posture' } }
    })
  }

  if (invoice && invoice.overage > 0) {
    alerts.push({
      key: 'metering-overage',
      severity: 'warning',
      msgKey: 'notify.msg.overage',
      params: { amount: invoice.overage },
      route: { name: 'console', params: { tab: 'recommend' }, query: { sub: 'metering' } }
    })
  }

  if (readiness && !readiness.readyToSign) {
    alerts.push({
      key: 'deal-readiness',
      severity: 'info',
      msgKey: 'notify.msg.readiness',
      params: { score: readiness.score, blockers: readiness.blockers?.length ?? 0 },
      route: { name: 'console', params: { tab: 'showcase' }, query: { sub: 'pipeline' } }
    })
  }

  return alerts
}

export function createInbox({ limit = 50 } = {}) {
  const items = new Map() // key → notification

  function push(alert, now = Date.now()) {
    const existing = items.get(alert.key)
    if (existing) {
      existing.at = now
      existing.count += 1
      existing.severity = alert.severity
      existing.params = alert.params
      return existing
    }
    const item = { ...alert, at: now, count: 1, read: false }
    items.set(alert.key, item)
    evict()
    return item
  }

  // Beyond the cap, evict oldest READ items first — an unread critical
  // is never silently dropped (soft cap over silent loss).
  function evict() {
    if (items.size <= limit) return
    const read = [...items.values()].filter(i => i.read).sort((a, b) => a.at - b.at)
    for (const r of read) {
      if (items.size <= limit) break
      items.delete(r.key)
    }
  }

  return {
    push,
    markRead(key) { const i = items.get(key); if (i) i.read = true },
    markAllRead() { for (const i of items.values()) i.read = true },
    unreadCount: () => [...items.values()].filter(i => !i.read).length,
    size: () => items.size,
    list({ unreadOnly = false } = {}) {
      return [...items.values()]
        .filter(i => !unreadOnly || !i.read)
        .sort((a, b) => b.at - a.at || Number(a.read) - Number(b.read))
    }
  }
}
