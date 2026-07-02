<script setup>
import { ref, nextTick } from 'vue'

const messages = ref([
  { role: 'system', text: 'Deal Copilot ready. Ask for drafting, translation, or risk-checking.' },
  { role: 'user', text: 'Draft an opening reply to a Japanese retailer who wants to distribute our brand. Tone: warm and respectful.' },
  { role: 'ai',
    text: `Tanaka-san,\n\nThank you for reaching out — we are honored by your interest in distributing our brand in Japan. Your store has built a reputation we admire deeply, and we would welcome a conversation about partnering for the next launch.\n\nTo move things forward, could you share:\n  • Target launch window and initial SKU coverage\n  • Marketing co-op expectations\n  • Logistics partner you typically work with\n\nWe can prepare a sample localized campaign within five working days to demonstrate fit.\n\n敬具,\n[Your name]`,
    risks: [
      { tag: 'Tone', level: 'ok', note: 'Reads respectful and confident — appropriate for first contact in JP.' },
      { tag: 'Legal', level: 'warn', note: 'Avoid committing to "exclusivity" until DPA & territory terms are signed.' },
      { tag: 'Localization', level: 'ok', note: 'Honorifics used correctly; closing in Japanese improves rapport.' }
    ]
  }
])

const input = ref('')
const sending = ref(false)
const listRef = ref(null)

const presets = [
  'Translate the last reply into Japanese (keigo).',
  'Push back politely on a 15% price discount request.',
  'Flag legal risks in this distribution proposal.',
  'Summarize the deal in 5 bullets for the founder.'
]

async function send(text) {
  const t = text ?? input.value
  if (!t.trim() || sending.value) return
  messages.value.push({ role: 'user', text: t })
  input.value = ''
  sending.value = true
  await nextTick(); scroll()

  await new Promise(r => setTimeout(r, 700))

  const reply = mockReply(t)
  messages.value.push(reply)
  sending.value = false
  await nextTick(); scroll()
}

function scroll() {
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}

function mockReply(t) {
  const lower = t.toLowerCase()
  if (lower.includes('japanese') || lower.includes('keigo') || lower.includes('translate')) {
    return { role: 'ai',
      text: `田中様\n\nご連絡いただき、誠にありがとうございます。日本市場における当ブランドの展開にご関心をお寄せいただき、大変光栄でございます。\n\n以下の点について、ご共有いただけますでしょうか。\n  • 想定されるローンチ時期と初回 SKU 数\n  • マーケティング協業のご希望範囲\n  • 通常ご利用の物流パートナー\n\n5 営業日以内に、貴店向けにローカライズしたキャンペーン案をお届けいたします。\n\n何卒よろしくお願い申し上げます。`,
      risks: [
        { tag: 'Honorifics', level: 'ok', note: 'Keigo level appropriate for first formal contact.' }
      ]
    }
  }
  if (lower.includes('discount') || lower.includes('price') || lower.includes('15%')) {
    return { role: 'ai',
      text: 'A 15% list-price discount would push us below our wholesale floor in this category. We can instead offer:\n  • 8% volume rebate above 5,000 units / quarter\n  • Joint marketing fund worth 4% of net revenue\n  • Priority allocation during peak season\n\nThis structure protects margin for both sides while rewarding scale.',
      risks: [
        { tag: 'Margin', level: 'ok', note: 'Counter-offer keeps gross margin above 42%.' },
        { tag: 'Antitrust', level: 'warn', note: 'Rebate tiers must be offered uniformly to comparable partners.' }
      ]
    }
  }
  if (lower.includes('legal') || lower.includes('risk')) {
    return { role: 'ai',
      text: 'Top risks flagged in the proposal:\n  1. Exclusivity clause has no carve-out for e-commerce — re-scope to brick-and-mortar.\n  2. IP indemnity is one-sided; add mutual indemnification.\n  3. Termination requires 12 months notice — request 6 months with cause.\n  4. Data flow to retailer CRM lacks a DPA under APPI.',
      risks: [
        { tag: 'Exclusivity', level: 'warn', note: 'Carve out direct-to-consumer & owned channels.' },
        { tag: 'Data', level: 'risk', note: 'APPI cross-border consent required before customer data flows out.' },
        { tag: 'Termination', level: 'warn', note: '12 months is unusually long for this market.' }
      ]
    }
  }
  if (lower.includes('summarize') || lower.includes('summary') || lower.includes('5 bullets')) {
    return { role: 'ai',
      text: '  • Partner: Japanese retailer, 42 owned stores, founded 1998.\n  • Ask: Distribute Q1 launch, 12 SKUs, exclusivity in JP off-line channels.\n  • Marketing: 4% co-op fund, joint launch event in Tokyo.\n  • Risks: Exclusivity scope, IP indemnity, data flow under APPI.\n  • Decision needed: Yes/No to exclusivity carve-out by Friday.',
      risks: [{ tag: 'Action', level: 'ok', note: 'Owner: founder. Deadline: Friday.' }] }
  }
  return { role: 'ai',
    text: 'I can help draft, translate or risk-check anything for this deal. Try one of the presets below.',
    risks: [] }
}
</script>

<template>
  <div class="copilot card">
    <div class="convo" ref="listRef">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="bubble">
          <div class="role" v-if="m.role !== 'system'">{{ m.role === 'ai' ? 'Deal Copilot' : 'You' }}</div>
          <div class="text">{{ m.text }}</div>
          <div v-if="m.risks && m.risks.length" class="risks">
            <div v-for="(r, j) in m.risks" :key="j" class="risk" :class="r.level">
              <span class="rtag">{{ r.tag }}</span>
              <span class="rnote">{{ r.note }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-if="sending" class="msg ai">
        <div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>
      </div>
    </div>

    <div class="presets">
      <button v-for="p in presets" :key="p" class="preset" @click="send(p)" :disabled="sending" type="button">
        {{ p }}
      </button>
    </div>

    <form class="input-row" @submit.prevent="send()">
      <input v-model="input" type="text" placeholder="Ask the copilot…" :disabled="sending" />
      <button type="submit" class="btn btn-primary" :disabled="sending || !input.trim()">Send</button>
    </form>
  </div>
</template>

<style scoped>
.copilot { padding: 0; overflow: hidden; }
.convo { padding: 24px; max-height: 520px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
.msg { display: flex; }
.msg.user { justify-content: flex-end; }
.msg.system { justify-content: center; }
.msg.system .bubble { background: transparent; color: var(--text-dim); font-size: 12px; padding: 4px 8px; border: 1px dashed var(--border); }
.bubble {
  max-width: 80%; padding: 14px 16px; border-radius: 14px;
  background: var(--surface); border: 1px solid var(--border);
  white-space: pre-wrap; line-height: 1.55; font-size: 14px;
}
.msg.user .bubble { background: linear-gradient(135deg, rgba(124,92,255,.25), rgba(34,211,238,.18)); border-color: rgba(124,92,255,.35); color: #fff; }
.role { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .08em; margin-bottom: 6px; }
.text { color: var(--text); }

.risks { margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--border); display: flex; flex-direction: column; gap: 6px; }
.risk { display: flex; gap: 10px; align-items: flex-start; font-size: 12px; }
.rtag { padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; flex-shrink: 0; }
.risk.ok .rtag { background: rgba(52, 211, 153, .15); color: #6ee7b7; }
.risk.warn .rtag { background: rgba(251, 191, 36, .15); color: #fcd34d; }
.risk.risk .rtag { background: rgba(248, 113, 113, .15); color: #fca5a5; }
.rnote { color: var(--text-dim); }

.typing { display: inline-flex; gap: 5px; padding: 4px 0; }
.typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--text-dim); animation: tp 1s ease-in-out infinite; }
.typing span:nth-child(2) { animation-delay: .15s; }
.typing span:nth-child(3) { animation-delay: .3s; }
@keyframes tp { 0%, 100% { opacity: .3; transform: translateY(0); } 50% { opacity: 1; transform: translateY(-3px); } }

.presets { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 24px; border-top: 1px solid var(--border); background: rgba(0,0,0,.2); }
.preset { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 6px 12px; border-radius: 999px; font-size: 12px; cursor: pointer; }
.preset:hover:not(:disabled) { border-color: var(--primary); }
.preset:disabled { opacity: .5; cursor: not-allowed; }

.input-row { display: flex; gap: 8px; padding: 16px 20px; border-top: 1px solid var(--border); background: var(--bg-2); }
.input-row input { flex: 1; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; color: var(--text); font-size: 14px; outline: none; }
.input-row input:focus { border-color: var(--primary); }
</style>
