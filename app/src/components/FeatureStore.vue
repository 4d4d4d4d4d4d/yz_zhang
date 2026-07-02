<script setup>
import { ref, computed } from 'vue'

const entities = [
  { id: 'user',     name: 'User',     pk: 'user_id',     volume: '12.4M', features: 18 },
  { id: 'product',  name: 'Product',  pk: 'sku',         volume: '38K',   features: 14 },
  { id: 'campaign', name: 'Campaign', pk: 'campaign_id', volume: '1,284', features: 9 }
]

const features = {
  user: [
    { name: 'user_id',                 type: 'string',  serving: 'online',  freshness: 'live',     qps: 2840, hit: 99, owner: 'platform', schema: 'PII · hashed' },
    { name: 'country',                 type: 'string',  serving: 'online',  freshness: 'live',     qps: 2840, hit: 99, owner: 'platform', schema: 'ISO 3166' },
    { name: 'age_bucket',              type: 'enum',    serving: 'online',  freshness: 'live',     qps: 2820, hit: 98, owner: 'identity', schema: '5 buckets' },
    { name: 'interests_30d_embed',     type: 'vector',  serving: 'online',  freshness: '5m',       qps: 2840, hit: 92, owner: 'ml',       schema: 'float32[256]' },
    { name: 'avg_order_value_90d',     type: 'float',   serving: 'online',  freshness: '15m',      qps: 1240, hit: 88, owner: 'growth',   schema: '$ USD' },
    { name: 'sessions_7d',             type: 'int',     serving: 'online',  freshness: '1m',       qps: 2840, hit: 96, owner: 'analytics', schema: 'count' },
    { name: 'churn_score_v3',          type: 'float',   serving: 'online',  freshness: '6h',       qps: 480,  hit: 94, owner: 'ml',       schema: '[0,1]' },
    { name: 'cohort_label',            type: 'string',  serving: 'batch',   freshness: 'daily',    qps: 0,    hit: 100,owner: 'analytics', schema: '40+ cohorts' }
  ],
  product: [
    { name: 'sku',                     type: 'string',  serving: 'online',  freshness: 'live',     qps: 1820, hit: 99, owner: 'catalog',  schema: 'unique' },
    { name: 'category',                type: 'enum',    serving: 'online',  freshness: 'live',     qps: 1820, hit: 99, owner: 'catalog',  schema: '12 cats' },
    { name: 'embedding_v4',            type: 'vector',  serving: 'online',  freshness: 'on_update',qps: 1820, hit: 94, owner: 'ml',       schema: 'float32[512]' },
    { name: 'inventory_units',         type: 'int',     serving: 'online',  freshness: '30s',      qps: 1620, hit: 86, owner: 'ops',      schema: 'count' },
    { name: 'price_usd',               type: 'float',   serving: 'online',  freshness: '1h',       qps: 1820, hit: 99, owner: 'pricing',  schema: '$ USD' }
  ],
  campaign: [
    { name: 'campaign_id',             type: 'string',  serving: 'online',  freshness: 'live',     qps: 940,  hit: 99, owner: 'growth',   schema: 'unique' },
    { name: 'channel',                 type: 'enum',    serving: 'online',  freshness: 'live',     qps: 940,  hit: 99, owner: 'growth',   schema: 'TT/Meta/G/YT' },
    { name: 'creative_winrate_7d',     type: 'float',   serving: 'online',  freshness: '10m',      qps: 720,  hit: 88, owner: 'analytics', schema: '[0,1]' },
    { name: 'audience_segments',       type: 'list',    serving: 'batch',   freshness: 'daily',    qps: 0,    hit: 100,owner: 'growth',   schema: 'string[]' }
  ]
}

const active = ref('user')
const cur = computed(() => features[active.value])
</script>

<template>
  <div class="fs">
    <div class="card head">
      <div>
        <div class="kicker">Feature store</div>
        <h3>Entity registry · {{ entities.length }} entities · {{ entities.reduce((s, e) => s + e.features, 0) }} features</h3>
        <p class="meta">Online + batch feature views, lineage and schema enforced via contract checks at write time.</p>
      </div>
      <div class="health">
        <div><div class="hn ok-color">99.94%</div><div class="hl">Serving SLO</div></div>
        <div><div class="hn">{{ cur.reduce((s, f) => s + f.qps, 0).toLocaleString() }}</div><div class="hl">QPS · {{ active }}</div></div>
        <div><div class="hn">{{ Math.round(cur.reduce((s, f) => s + f.hit, 0) / cur.length) }}%</div><div class="hl">Avg cache hit</div></div>
      </div>
    </div>

    <div class="entity-row">
      <button v-for="e in entities" :key="e.id"
        class="ent" :class="{ on: active === e.id }"
        @click="active = e.id" type="button">
        <div class="ent-name">{{ e.name }}</div>
        <div class="ent-meta">pk · <code>{{ e.pk }}</code></div>
        <div class="ent-stats">
          <span>{{ e.volume }} rows</span>
          <span class="dot">·</span>
          <span>{{ e.features }} features</span>
        </div>
      </button>
    </div>

    <div class="card">
      <div class="hh">
        <h3>{{ entities.find(e => e.id === active).name }} features</h3>
        <span class="meta">{{ cur.filter(f => f.serving === 'online').length }} online · {{ cur.filter(f => f.serving === 'batch').length }} batch</span>
      </div>
      <table class="t">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Serving</th>
            <th>Freshness</th>
            <th class="num">QPS</th>
            <th class="num">Cache hit</th>
            <th>Owner</th>
            <th>Schema</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in cur" :key="f.name">
            <td><code>{{ f.name }}</code></td>
            <td><span class="ty" :class="f.type">{{ f.type }}</span></td>
            <td><span class="sv" :class="f.serving">{{ f.serving }}</span></td>
            <td class="dimc">{{ f.freshness }}</td>
            <td class="num">{{ f.qps ? f.qps.toLocaleString() : '—' }}</td>
            <td class="num">
              <span class="hit" :class="f.hit >= 95 ? 'ok' : f.hit >= 85 ? 'warn' : 'risk'">{{ f.hit }}%</span>
            </td>
            <td class="dimc">{{ f.owner }}</td>
            <td class="dimc"><code class="sm-code">{{ f.schema }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card lineage">
      <h3>Lineage · {{ active }}</h3>
      <p class="meta">Sources flowing into online + batch stores.</p>
      <div class="lin">
        <div class="ln-col">
          <div class="ln-h">Sources</div>
          <div class="ln-it source">Postgres · prod-db</div>
          <div class="ln-it source">Kafka · events.{{ active }}.v3</div>
          <div class="ln-it source">S3 · warehouse</div>
        </div>
        <div class="arrow"></div>
        <div class="ln-col">
          <div class="ln-h">Transforms</div>
          <div class="ln-it tx">Flink · enrichment</div>
          <div class="ln-it tx">Spark · batch nightly</div>
        </div>
        <div class="arrow"></div>
        <div class="ln-col">
          <div class="ln-h">Stores</div>
          <div class="ln-it store online">Redis online · {{ active }}_view_v4</div>
          <div class="ln-it store batch">Iceberg batch · {{ active }}_features</div>
        </div>
        <div class="arrow"></div>
        <div class="ln-col">
          <div class="ln-h">Consumers</div>
          <div class="ln-it consumer">rec-v17 (canary)</div>
          <div class="ln-it consumer">rec-v16 (prod)</div>
          <div class="ln-it consumer">churn-v3 (batch)</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fs { display: flex; flex-direction: column; gap: 16px; }
.head { padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.meta { color: var(--text-dim); font-size: 13px; margin: 4px 0 0; }
.health { display: flex; gap: 18px; }
.hn { font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; }
.ok-color { color: var(--success); }
.hl { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-top: 4px; }

.entity-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.ent { padding: 14px 16px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); cursor: pointer; text-align: left; color: var(--text); transition: border-color .15s; }
.ent:hover { border-color: var(--primary); }
.ent.on { border-color: var(--primary); background: rgba(124, 92, 255, .1); }
.ent-name { font-weight: 700; font-size: 15px; }
.ent-meta { font-size: 11px; color: var(--text-dim); margin: 4px 0 8px; }
.ent-meta code, code { background: var(--surface-2); padding: 1px 6px; border-radius: 4px; font-size: 11px; font-family: ui-monospace, monospace; }
.ent-stats { display: flex; gap: 6px; font-size: 11px; color: var(--text-dim); align-items: center; }
.ent-stats .dot { color: var(--border); }

.hh { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; }

.t { width: 100%; border-collapse: collapse; font-size: 12px; }
.t th { text-align: left; padding: 8px 10px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); font-weight: 700; }
.t th.num { text-align: right; }
.t td { padding: 10px; border-bottom: 1px dashed var(--border); }
.t td.num { text-align: right; font-variant-numeric: tabular-nums; }
.t td.dimc { color: var(--text-dim); }
.sm-code { font-size: 10px; }

.ty { font-size: 10px; padding: 2px 7px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.ty.string { background: rgba(124, 92, 255, .15); color: #c4b5fd; }
.ty.int, .ty.float { background: rgba(34, 211, 238, .15); color: #67e8f9; }
.ty.enum { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.ty.vector { background: rgba(255, 122, 217, .15); color: #f5d0fe; }
.ty.list { background: rgba(52, 211, 153, .15); color: #6ee7b7; }

.sv { font-size: 10px; padding: 2px 7px; border-radius: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.sv.online { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.sv.batch { background: var(--surface-2); color: var(--text-dim); }

.hit { padding: 2px 7px; border-radius: 5px; font-weight: 700; font-size: 11px; }
.hit.ok { background: rgba(52, 211, 153, .12); color: #6ee7b7; }
.hit.warn { background: rgba(251, 191, 36, .12); color: #fcd34d; }
.hit.risk { background: rgba(248, 113, 113, .12); color: #fca5a5; }

.lineage { padding: 20px; }
.lin { display: grid; grid-template-columns: 1fr 24px 1fr 24px 1fr 24px 1fr; gap: 12px; align-items: center; margin-top: 14px; }
.ln-col { display: flex; flex-direction: column; gap: 6px; }
.ln-h { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; font-weight: 700; margin-bottom: 4px; }
.ln-it { padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); font-size: 12px; }
.ln-it.source { border-color: rgba(96, 165, 250, .35); background: rgba(96, 165, 250, .06); }
.ln-it.tx { border-color: rgba(124, 92, 255, .35); background: rgba(124, 92, 255, .06); }
.ln-it.store { font-weight: 600; }
.ln-it.online { border-color: rgba(52, 211, 153, .35); background: rgba(52, 211, 153, .06); }
.ln-it.batch { border-color: var(--border); background: var(--surface-2); }
.ln-it.consumer { border-color: rgba(255, 122, 217, .35); background: rgba(255, 122, 217, .06); }
.arrow { height: 2px; background: var(--text-dim); position: relative; opacity: .5; }
.arrow::after { content: ''; position: absolute; right: -1px; top: -3px; border: 4px solid transparent; border-left: 6px solid var(--text-dim); }

@media (max-width: 1024px) {
  .entity-row { grid-template-columns: 1fr; }
  .lin { grid-template-columns: 1fr; }
  .arrow { width: 2px; height: 16px; margin: 0 auto; }
  .arrow::after { right: -3px; top: auto; bottom: -1px; border: 4px solid transparent; border-top: 6px solid var(--text-dim); border-left: 4px solid transparent; }
  .t { font-size: 11px; }
  .t th:nth-child(7), .t td:nth-child(7), .t th:nth-child(8), .t td:nth-child(8) { display: none; }
}
</style>
