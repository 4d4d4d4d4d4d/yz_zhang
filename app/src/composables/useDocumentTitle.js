// Spec 28 — localized document.title synced to route + locale.
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

// Pure title composer — tested without a DOM.
export function composeTitle({ pageTitle, brand, section }) {
  const parts = [pageTitle, section].filter(Boolean)
  const head = parts.join(' · ')
  return head ? `${head} · ${brand}` : brand
}

export function useDocumentTitle() {
  const route = useRoute()
  const { t } = useI18n()

  function apply() {
    if (typeof document === 'undefined') return
    const brand = t('brand')
    const key = route.meta?.titleKey
    const pageTitle = key ? t(key) : ''
    const section = route.name === 'console' && route.params.tab
      ? t(`console.s.${route.params.tab}.title`)
      : ''
    document.title = composeTitle({ pageTitle, brand, section })
  }

  watch(() => [route.fullPath, route.name], apply, { immediate: true })
  // Re-run on locale change: watch the translated brand as a cheap proxy.
  watch(() => t('brand'), apply)
}
