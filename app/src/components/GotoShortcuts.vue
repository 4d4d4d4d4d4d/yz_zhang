<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { resolveGoto } from '../logic/shortcuts.js'

// Spec 31 — GitHub/Linear-style `g` then a key to jump between areas.
const router = useRouter()
let armed = false
let timer = null

function isTyping(el) {
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

function onKey(e) {
  if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) { disarm(); return }
  if (armed) {
    const route = resolveGoto(e.key)
    disarm()
    if (route) { e.preventDefault(); router.push(route) }
    return
  }
  if (e.key === 'g') {
    armed = true
    timer = setTimeout(disarm, 1500) // arming window
  }
}
function disarm() { armed = false; if (timer) { clearTimeout(timer); timer = null } }

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => { window.removeEventListener('keydown', onKey); disarm() })
</script>

<template><!-- headless --></template>
