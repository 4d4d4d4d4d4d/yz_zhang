<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const sessions = ref(14)
const rps = ref(2840)
const latency = ref(86)

let timer
onMounted(() => {
  timer = setInterval(() => {
    sessions.value = Math.max(8, Math.min(24, sessions.value + Math.round((Math.random() - .5) * 3)))
    rps.value = Math.round(rps.value + (Math.random() - .5) * 280)
    latency.value = Math.max(58, Math.min(140, latency.value + Math.round((Math.random() - .5) * 14)))
  }, 1800)
})
onBeforeUnmount(() => clearInterval(timer))

const items = [
  { k: 'SSO', v: 'SAML / OIDC', state: 'ok' },
  { k: 'MFA', v: 'WebAuthn',  state: 'ok' },
  { k: 'RBAC', v: '6 roles · 18 scopes', state: 'ok' },
  { k: 'Region', v: 'JP · EU · US', state: 'ok' },
  { k: 'Encryption', v: 'AES-256 · TLS 1.3', state: 'ok' },
  { k: 'KMS', v: 'Auto-rotate 90d', state: 'ok' }
]
</script>

<template>
  <div class="ribbon card">
    <div class="left">
      <span class="live"><span class="dot"></span> Workspace live</span>
      <div class="kv-row">
        <div v-for="it in items" :key="it.k" class="kv">
          <span class="k">{{ it.k }}</span>
          <span class="v">{{ it.v }}</span>
          <span class="state" :class="it.state">✓</span>
        </div>
      </div>
    </div>
    <div class="right">
      <div class="metric">
        <div class="m-num">{{ sessions }}</div>
        <div class="m-lbl">Sessions</div>
      </div>
      <div class="metric">
        <div class="m-num">{{ rps.toLocaleString() }}<span class="m-unit">/s</span></div>
        <div class="m-lbl">API req</div>
      </div>
      <div class="metric">
        <div class="m-num">{{ latency }}<span class="m-unit">ms</span></div>
        <div class="m-lbl">p95</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ribbon {
  display: flex; justify-content: space-between; align-items: center; gap: 24px;
  padding: 14px 20px; border-radius: 14px;
  background: linear-gradient(180deg, rgba(124,92,255,.08), rgba(34,211,238,.04));
  border-color: rgba(124,92,255,.25);
  margin-bottom: 20px; flex-wrap: wrap;
}
.left { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.live { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; color: var(--success); white-space: nowrap; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 10px var(--success); animation: pl 1.4s ease-in-out infinite; }
@keyframes pl { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

.kv-row { display: flex; gap: 16px; flex-wrap: wrap; }
.kv { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 5px 10px; border-radius: 8px; background: rgba(0,0,0,.2); }
.k { color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; font-size: 10px; font-weight: 700; }
.v { color: var(--text); }
.state { font-size: 10px; }
.state.ok { color: var(--success); }

.right { display: flex; gap: 18px; }
.metric { text-align: right; min-width: 60px; }
.m-num { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1; }
.m-unit { font-size: 11px; color: var(--text-dim); margin-left: 2px; }
.m-lbl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 3px; }

@media (max-width: 900px) {
  .ribbon { flex-direction: column; align-items: flex-start; }
  .right { width: 100%; justify-content: space-between; }
}
</style>
