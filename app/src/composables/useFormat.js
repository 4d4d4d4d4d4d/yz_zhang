// Spec 33 — binds the locale-aware formatters (logic/format.js) to the
// operator's current i18n locale. Components call `const { money } = useFormat()`
// and never touch Intl or hardcode a locale/`$` again.

import { useI18n } from 'vue-i18n'
import { num, compact, money, pct } from '../logic/format.js'

export function useFormat() {
  const { locale } = useI18n()
  const L = () => locale.value
  return {
    num: (n, opts) => num(n, L(), opts),
    compact: n => compact(n, L()),
    money: (n, opts = {}) => money(n, { locale: L(), ...opts }),
    pct: (n, opts = {}) => pct(n, { locale: L(), ...opts })
  }
}
