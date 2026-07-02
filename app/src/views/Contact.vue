<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import SectionHeader from '../components/SectionHeader.vue'
import PartnerMatcher from '../components/PartnerMatcher.vue'
const { t } = useI18n()

const form = ref({ name: '', email: '', company: '', region: '', role: 'brand', message: '' })
const status = ref('idle') // idle | sending | success | error

const valid = computed(() => form.value.name && form.value.email && form.value.company && form.value.message)

async function submit() {
  if (!valid.value) { status.value = 'error'; return }
  status.value = 'sending'
  await new Promise(r => setTimeout(r, 900))
  status.value = 'success'
}
</script>

<template>
  <section class="section">
    <div class="container">
      <SectionHeader :eyebrow="t('contact.eyebrow')"
        :title="t('contact.title')" :subtitle="t('contact.subtitle')" />

      <div class="contact-grid">
        <form class="card form" @submit.prevent="submit">
          <div class="row two">
            <label>{{ t('contact.name') }} *
              <input v-model="form.name" type="text" required />
            </label>
            <label>{{ t('contact.email') }} *
              <input v-model="form.email" type="email" required />
            </label>
          </div>
          <div class="row two">
            <label>{{ t('contact.company') }} *
              <input v-model="form.company" type="text" required />
            </label>
            <label>{{ t('contact.region') }}
              <input v-model="form.region" type="text" placeholder="US, JP, BR…" />
            </label>
          </div>
          <label>{{ t('contact.role') }}
            <select v-model="form.role">
              <option value="brand">{{ t('contact.roles.brand') }}</option>
              <option value="agency">{{ t('contact.roles.agency') }}</option>
              <option value="partner">{{ t('contact.roles.partner') }}</option>
              <option value="other">{{ t('contact.roles.other') }}</option>
            </select>
          </label>
          <label>{{ t('contact.message') }} *
            <textarea v-model="form.message" rows="5" required></textarea>
          </label>

          <div class="form-foot">
            <button type="submit" class="btn btn-primary" :disabled="status === 'sending' || status === 'success'">
              <span v-if="status === 'sending'">{{ t('contact.sending') }}</span>
              <span v-else-if="status === 'success'">✓ {{ t('contact.success') }}</span>
              <span v-else>{{ t('contact.submit') }} →</span>
            </button>
            <span v-if="status === 'error'" class="err">{{ t('contact.error') }}</span>
          </div>
        </form>

        <aside class="side">
          <div class="card">
            <h3>{{ t('contact.or') }}</h3>
            <a class="link-row" :href="`mailto:${t('contact.email_us')}`">
              <span>📧</span><span>{{ t('contact.email_us') }}</span>
            </a>
            <a class="link-row" href="#">
              <span>📅</span><span>{{ t('contact.book_call') }}</span>
            </a>
            <a class="link-row" href="#">
              <span>💬</span><span>WeChat / LINE / WhatsApp</span>
            </a>
          </div>

          <div class="card">
            <div class="kicker">Reply SLA</div>
            <div class="sla">1 business day</div>
            <p>Partner managers in Shanghai, Tokyo, Singapore and SF cover your timezone.</p>
          </div>
        </aside>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="container">
      <SectionHeader title="Partner matcher"
        subtitle="Tell us your category and target market — AdForge surfaces partners we can introduce you to from our network." />
      <PartnerMatcher />
    </div>
  </section>
</template>

<style scoped>
.contact-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 28px; }
.form { display: flex; flex-direction: column; gap: 18px; }
.row.two { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
label { display: flex; flex-direction: column; gap: 8px; font-size: 13px; color: var(--text-dim); }
input, select, textarea {
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 12px 14px; color: var(--text); font-size: 14px; font-family: inherit; outline: none;
}
input:focus, select:focus, textarea:focus { border-color: var(--primary); }
textarea { resize: vertical; }
.form-foot { display: flex; align-items: center; gap: 16px; margin-top: 4px; }
.form-foot :deep(.btn) { min-width: 200px; justify-content: center; }
.err { color: var(--danger); font-size: 13px; }

.side { display: flex; flex-direction: column; gap: 16px; }
.link-row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px dashed var(--border); color: var(--text); font-size: 14px; }
.link-row:last-child { border-bottom: 0; }
.link-row:hover { color: var(--primary-2); }
.kicker { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .1em; }
.sla { font-size: 32px; font-weight: 800; margin: 6px 0 8px; }
.side p { margin: 0; }

@media (max-width: 900px) {
  .contact-grid { grid-template-columns: 1fr; }
  .row.two { grid-template-columns: 1fr; }
}
</style>
