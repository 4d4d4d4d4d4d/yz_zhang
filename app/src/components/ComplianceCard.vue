<script setup>
const items = [
  { region: 'EU · GDPR', desc: 'Personal data minimization, opt-in tracking, EU-hosted rendering option.', tag: 'Active' },
  { region: 'US · CCPA / CPRA', desc: 'Consumer opt-out signals, data processing agreements, retention controls.', tag: 'Active' },
  { region: 'JP · APPI', desc: 'Cross-border transfer disclosures, localization-aware consent flows.', tag: 'Active' },
  { region: 'Brand safety', desc: 'Generated assets pass through 14 content-safety checks before export.', tag: 'Built-in' },
  { region: 'Content provenance', desc: 'C2PA signatures embedded into every render to certify AI origin.', tag: 'Built-in' },
  { region: 'Human review', desc: 'On-demand SLA review by trained moderators in 4 regions.', tag: 'Add-on' }
]
</script>

<template>
  <div class="grid grid-3">
    <div v-for="(it, i) in items" :key="i" class="card cmp">
      <div class="head">
        <span class="shield" aria-hidden="true">🛡</span>
        <span class="tag" :class="it.tag.toLowerCase().replace(' ', '-')">{{ it.tag }}</span>
      </div>
      <h3>{{ it.region }}</h3>
      <p>{{ it.desc }}</p>
    </div>
  </div>
</template>

<style scoped>
.cmp { display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; justify-content: space-between; align-items: center; }
.shield { font-size: 22px; }
.tag { font-size: 11px; padding: 4px 10px; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; }
.tag.active { color: var(--success); border-color: rgba(52, 211, 153, .4); background: rgba(52, 211, 153, .1); }
.tag.built-in { color: var(--primary-2); border-color: rgba(34, 211, 238, .4); background: rgba(34, 211, 238, .1); }
.cmp p { margin: 0; }
</style>
