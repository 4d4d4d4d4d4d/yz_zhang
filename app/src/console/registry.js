// Spec 20 — single source of truth for console section structure.
// Structure only: keys, icons, ordered sub-tab keys. No components, no
// i18n — safe to import from both the view and the test layer.

export const SECTIONS = [
  { key: 'recommend', icon: '🧠', subs: ['inputs', 'agents', 'registry', 'bandit', 'features', 'experiments', 'metering', 'tenant'] },
  { key: 'marketing', icon: '📈', subs: ['overview', 'control', 'attribution', 'audience', 'retention', 'forecast', 'revenue', 'upsell', 'funnel'] },
  { key: 'partners',  icon: '🤝', subs: ['network', 'pipeline', 'intel', 'outreach', 'forecast', 'territory', 'orders', 'commission'] },
  { key: 'deals',     icon: '📝', subs: ['room', 'playbook', 'workflow', 'library', 'obligations', 'analytics', 'cpq', 'revrec'] },
  { key: 'showcase',  icon: '🎬', subs: ['gallery', 'links', 'verification', 'pipeline'] },
  { key: 'immersive', icon: '🕶', subs: ['avatar', 'meeting', 'tour', 'field'] },
  { key: 'trust',     icon: '🛡', subs: ['posture', 'controls', 'heatmap', 'dpia', 'audit', 'policies', 'health', 'support'] }
]
