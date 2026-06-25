<script setup>
import { ref, computed } from 'vue'

const groups = ref([
  {
    op: 'and',
    rules: [
      { field: 'country', op: 'in',     value: 'JP, KR' },
      { field: 'age',     op: 'between', value: '18-34' }
    ]
  },
  {
    op: 'or',
    rules: [
      { field: 'interest', op: 'matches', value: 'K-beauty' },
      { field: 'engaged_with', op: 'is',  value: 'TikTok skincare creators' }
    ]
  }
])
const negate = ref([
  { field: 'purchased', op: 'is', value: 'competitor brand in last 30d' }
])

const fields = ['country', 'age', 'gender', 'interest', 'device', 'engaged_with', 'purchased', 'avg_order_value', 'lifecycle_stage']
const ops = ['is', 'is not', 'in', 'not in', 'matches', 'between', '>=', '<=']

function addRule(group) { group.rules.push({ field: 'country', op: 'in', value: '' }) }
function delRule(group, i) { group.rules.splice(i, 1) }
function addGroup() { groups.value.push({ op: 'and', rules: [{ field: 'country', op: 'in', value: '' }] }) }
function delGroup(i) { groups.value.splice(i, 1) }
function addExclusion() { negate.value.push({ field: 'purchased', op: 'is', value: '' }) }
function delExclusion(i) { negate.value.splice(i, 1) }

const ruleCount = computed(() =>
  groups.value.reduce((s, g) => s + g.rules.filter(r => r.value).length, 0) +
  negate.value.filter(r => r.value).length
)

const reach = computed(() => {
  const base = 12_400_000
  const ratio = Math.max(0.04, 0.6 - ruleCount.value * 0.07 + Math.random() * 0.02)
  return Math.round(base * ratio)
})
const overlap = computed(() => Math.round(28 - ruleCount.value * 2.4))
const ltv = computed(() => Math.round(64 + ruleCount.value * 5.8))

const savedSegments = [
  { name: 'JP Gen Z · K-beauty fans', reach: '1.42M', ltv: '$112' },
  { name: 'US Millennial parents · skincare lapsed', reach: '860K', ltv: '$148' },
  { name: 'BR new-mom · price-sensitive', reach: '2.1M', ltv: '$72' }
]
</script>

<template>
  <div class="ab">
    <div class="grid">
      <div class="card composer">
        <div class="h-row">
          <h3>Audience composition</h3>
          <span class="meta">{{ groups.length }} include groups · {{ negate.length }} exclusions</span>
        </div>

        <div v-for="(g, gi) in groups" :key="gi" class="group" :class="'op-' + g.op">
          <div class="g-head">
            <div class="g-tag">{{ g.op.toUpperCase() }}</div>
            <span class="g-info">Match any rule in this group</span>
            <button class="x" @click="delGroup(gi)" type="button" title="Delete group">×</button>
          </div>
          <div v-for="(r, ri) in g.rules" :key="ri" class="rule">
            <select v-model="r.field">
              <option v-for="f in fields" :key="f">{{ f }}</option>
            </select>
            <select v-model="r.op">
              <option v-for="o in ops" :key="o">{{ o }}</option>
            </select>
            <input v-model="r.value" placeholder="value" />
            <button class="x" @click="delRule(g, ri)" type="button">×</button>
          </div>
          <div class="g-foot">
            <button class="mini" @click="addRule(g)" type="button">+ Rule</button>
            <div class="op-toggle">
              <button :class="{ on: g.op === 'and' }" @click="g.op = 'and'" type="button">AND</button>
              <button :class="{ on: g.op === 'or' }" @click="g.op = 'or'" type="button">OR</button>
            </div>
          </div>
        </div>

        <div class="between">
          <span>AND</span><span class="line"></span>
        </div>

        <div class="group exclude">
          <div class="g-head">
            <div class="g-tag neg">NOT</div>
            <span class="g-info">Exclude anyone matching these rules</span>
            <button class="mini" @click="addExclusion" type="button">+ Exclusion</button>
          </div>
          <div v-for="(r, ri) in negate" :key="ri" class="rule">
            <select v-model="r.field">
              <option v-for="f in fields" :key="f">{{ f }}</option>
            </select>
            <select v-model="r.op">
              <option v-for="o in ops" :key="o">{{ o }}</option>
            </select>
            <input v-model="r.value" placeholder="value" />
            <button class="x" @click="delExclusion(ri)" type="button">×</button>
          </div>
        </div>

        <button class="btn btn-ghost sm add-group" @click="addGroup" type="button">+ Add include group</button>
      </div>

      <div class="card est">
        <h3>Live estimate</h3>
        <div class="big grad-text">{{ (reach / 1000000).toFixed(2) }}M</div>
        <div class="big-sub">Daily eligible users</div>

        <div class="bars">
          <div class="b-row">
            <span class="bl">Reach precision</span>
            <div class="bt"><div class="bf" :style="{ width: Math.min(100, ruleCount * 14) + '%' }"></div></div>
            <span class="bv">{{ Math.min(100, ruleCount * 14) }}%</span>
          </div>
          <div class="b-row">
            <span class="bl">Overlap (other segs)</span>
            <div class="bt"><div class="bf overlap" :style="{ width: overlap + '%' }"></div></div>
            <span class="bv">{{ overlap }}%</span>
          </div>
          <div class="b-row">
            <span class="bl">Pred. LTV</span>
            <div class="bt"><div class="bf ltv" :style="{ width: Math.min(100, ltv) + '%' }"></div></div>
            <span class="bv">${{ ltv }}</span>
          </div>
        </div>

        <div class="est-actions">
          <button class="btn btn-primary sm" type="button">Save segment</button>
          <button class="btn btn-ghost sm" type="button">Push to ad accounts</button>
        </div>

        <div class="saved">
          <div class="kicker">Saved segments</div>
          <div v-for="s in savedSegments" :key="s.name" class="sv">
            <span class="sv-name">{{ s.name }}</span>
            <span class="sv-meta">{{ s.reach }} · LTV {{ s.ltv }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ab { display: flex; flex-direction: column; gap: 16px; }
.grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; align-items: flex-start; }
.h-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
.meta { color: var(--text-dim); font-size: 12px; }
.kicker { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }

.composer { padding: 20px; }
.group { border: 1px solid var(--border); border-radius: 12px; padding: 12px; background: var(--surface); margin-bottom: 12px; }
.group.op-and { border-color: rgba(124, 92, 255, .3); }
.group.op-or { border-color: rgba(34, 211, 238, .3); }
.group.exclude { border-color: rgba(248, 113, 113, .3); background: rgba(248, 113, 113, .04); }
.g-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.g-tag { padding: 3px 8px; border-radius: 5px; font-size: 10px; font-weight: 800; letter-spacing: .08em; background: rgba(124, 92, 255, .2); color: #c4b5fd; }
.g-tag.neg { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.g-info { font-size: 11px; color: var(--text-dim); }
.x { margin-left: auto; background: transparent; border: 1px solid var(--border); color: var(--text-dim); border-radius: 6px; width: 26px; height: 26px; cursor: pointer; font-size: 14px; line-height: 1; }
.x:hover { color: var(--danger); border-color: var(--danger); }
.mini { padding: 5px 10px; border-radius: 6px; background: var(--surface-2); border: 1px solid var(--border); color: var(--text); font-size: 11px; cursor: pointer; }
.mini:hover { border-color: var(--primary); }

.rule { display: grid; grid-template-columns: 1.2fr 1fr 1.6fr 30px; gap: 6px; align-items: center; margin-bottom: 6px; }
.rule:last-of-type { margin-bottom: 8px; }
.rule select, .rule input { background: var(--bg-2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text); font-size: 12px; outline: none; }
.rule select:focus, .rule input:focus { border-color: var(--primary); }

.g-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.op-toggle { display: inline-flex; padding: 2px; border-radius: 6px; background: var(--bg-2); border: 1px solid var(--border); gap: 2px; }
.op-toggle button { padding: 3px 10px; border-radius: 4px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; font-size: 10px; font-weight: 700; letter-spacing: .06em; }
.op-toggle button.on { background: linear-gradient(135deg, var(--primary), var(--primary-2)); color: #fff; }

.between { display: flex; align-items: center; gap: 10px; margin: 12px 0; font-size: 11px; letter-spacing: .1em; color: var(--text-dim); font-weight: 700; }
.between .line { flex: 1; height: 1px; background: var(--border); }
.add-group { width: 100%; justify-content: center; margin-top: 4px; }
.btn.sm { padding: 6px 12px; font-size: 12px; }

.est { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.big { font-size: 44px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.big-sub { color: var(--text-dim); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }

.bars { display: flex; flex-direction: column; gap: 10px; padding-top: 12px; border-top: 1px solid var(--border); }
.b-row { display: grid; grid-template-columns: 100px 1fr 50px; gap: 10px; align-items: center; font-size: 11px; }
.bl { color: var(--text-dim); text-transform: uppercase; letter-spacing: .06em; font-size: 10px; }
.bt { height: 5px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.bf { height: 100%; background: linear-gradient(90deg, var(--primary), var(--primary-2)); transition: width .25s ease; }
.bf.overlap { background: linear-gradient(90deg, #fcd34d, var(--accent)); }
.bf.ltv { background: linear-gradient(90deg, var(--success), var(--primary-2)); }
.bv { font-variant-numeric: tabular-nums; text-align: right; }

.est-actions { display: flex; gap: 8px; }
.est-actions :deep(.btn) { flex: 1; justify-content: center; }

.saved { padding-top: 16px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
.sv { display: flex; justify-content: space-between; padding: 8px 10px; border-radius: 8px; background: var(--surface); border: 1px solid var(--border); }
.sv-name { font-size: 12px; font-weight: 500; }
.sv-meta { font-size: 11px; color: var(--text-dim); }

@media (max-width: 900px) {
  .grid { grid-template-columns: 1fr; }
  .rule { grid-template-columns: 1fr; }
}
</style>
