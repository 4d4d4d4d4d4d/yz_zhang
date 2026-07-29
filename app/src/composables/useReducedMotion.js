// Spec 38 — reactive reduced-motion state. Combines the live OS media query
// with the persisted user preference and reflects the result onto <html>
// (`data-reduce-motion`) so global CSS honors a user override even when the OS
// setting says otherwise. Test/SSR-safe: guards matchMedia + document.

import { ref, computed, onMounted, onBeforeUnmount, watchEffect } from 'vue'
import { prefs, setMotionPref } from '../store/workspace.js'
import { resolveMotion } from '../logic/motion.js'

const QUERY = '(prefers-reduced-motion: reduce)'

export function useReducedMotion() {
  const osReduce = ref(false)
  let mq = null
  const onChange = e => { osReduce.value = e.matches }

  onMounted(() => {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      mq = window.matchMedia(QUERY)
      osReduce.value = mq.matches
      mq.addEventListener?.('change', onChange)
    }
  })
  onBeforeUnmount(() => mq?.removeEventListener?.('change', onChange))

  const reduced = computed(() => resolveMotion(osReduce.value, prefs.motion))

  watchEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-reduce-motion', String(reduced.value))
    }
  })

  return {
    reduced,
    motionPref: computed(() => prefs.motion),
    setMotionPref
  }
}
