<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const canvasRef = ref(null)
let raf = 0

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = Math.min(window.devicePixelRatio || 1, 2)

  function resize() {
    const r = canvas.getBoundingClientRect()
    canvas.width = r.width * dpr
    canvas.height = r.height * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }
  resize()
  window.addEventListener('resize', resize)

  const orbs = Array.from({ length: 6 }).map((_, i) => ({
    x: Math.random(),
    y: Math.random(),
    r: 80 + Math.random() * 160,
    hue: [265, 192, 320, 220, 280, 200][i],
    vx: (Math.random() - .5) * 0.0008,
    vy: (Math.random() - .5) * 0.0008,
    phase: Math.random() * Math.PI * 2
  }))

  let t = 0
  function frame() {
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    ctx.clearRect(0, 0, w, h)
    t += 0.008

    ctx.globalCompositeOperation = 'lighter'
    for (const o of orbs) {
      o.x += o.vx; o.y += o.vy
      if (o.x < 0 || o.x > 1) o.vx *= -1
      if (o.y < 0 || o.y > 1) o.vy *= -1
      const cx = o.x * w + Math.sin(t + o.phase) * 20
      const cy = o.y * h + Math.cos(t + o.phase) * 20
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, o.r)
      grad.addColorStop(0, `hsla(${o.hue}, 90%, 65%, 0.55)`)
      grad.addColorStop(1, `hsla(${o.hue}, 90%, 50%, 0)`)
      ctx.fillStyle = grad
      ctx.beginPath(); ctx.arc(cx, cy, o.r, 0, Math.PI * 2); ctx.fill()
    }
    ctx.globalCompositeOperation = 'source-over'
    raf = requestAnimationFrame(frame)
  }
  frame()
  onBeforeUnmount(() => {
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', resize)
  })
})
</script>

<template>
  <div class="video-hero">
    <canvas ref="canvasRef" aria-hidden="true"></canvas>
    <div class="overlay">
      <div class="ad-card ad-1">
        <div class="ad-img" style="--c1:#7c5cff;--c2:#22d3ee"></div>
        <div class="ad-tag">9:16 · TikTok JP</div>
      </div>
      <div class="ad-card ad-2">
        <div class="ad-img" style="--c1:#ff7ad9;--c2:#7c5cff"></div>
        <div class="ad-tag">1:1 · Meta US</div>
      </div>
      <div class="ad-card ad-3">
        <div class="ad-img" style="--c1:#22d3ee;--c2:#34d399"></div>
        <div class="ad-tag">16:9 · YouTube BR</div>
      </div>
      <div class="signal">
        <span class="dot"></span> Rendering 24 variants…
      </div>
    </div>
  </div>
</template>

<style scoped>
.video-hero {
  position: relative;
  border-radius: 22px; overflow: hidden;
  background: linear-gradient(180deg, #0c0c18, #07070b);
  border: 1px solid var(--border);
  aspect-ratio: 16 / 10;
  box-shadow: 0 40px 100px -40px rgba(124, 92, 255, .4);
}
canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
.overlay { position: absolute; inset: 0; display: grid; place-items: center; }

.ad-card {
  position: absolute; width: 28%; max-width: 220px;
  border-radius: 14px; overflow: hidden;
  background: rgba(20, 20, 31, .8);
  border: 1px solid rgba(255, 255, 255, .08);
  backdrop-filter: blur(10px);
  box-shadow: 0 20px 50px -20px rgba(0, 0, 0, .6);
  animation: float 6s ease-in-out infinite;
}
.ad-img {
  aspect-ratio: 9 / 16;
  background:
    radial-gradient(circle at 30% 30%, rgba(255,255,255,.15), transparent 40%),
    linear-gradient(135deg, var(--c1), var(--c2));
}
.ad-tag {
  font-size: 11px; color: #fff; padding: 8px 10px;
  background: rgba(0, 0, 0, .35); border-top: 1px solid rgba(255, 255, 255, .06);
}
.ad-1 { top: 12%; left: 8%; transform: rotate(-6deg); animation-delay: 0s; }
.ad-2 { top: 24%; right: 10%; transform: rotate(5deg); animation-delay: -2s; }
.ad-3 { bottom: 14%; left: 32%; transform: rotate(2deg); width: 32%; }
.ad-3 .ad-img { aspect-ratio: 16 / 9; }

@keyframes float {
  0%, 100% { translate: 0 0; }
  50% { translate: 0 -8px; }
}

.signal {
  position: absolute; bottom: 18px; right: 18px;
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-radius: 999px;
  background: rgba(0, 0, 0, .5); border: 1px solid var(--border);
  font-size: 12px; color: #d9d9ec;
}
.dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 12px var(--success);
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .4; } }

@media (max-width: 720px) {
  .ad-card { width: 36%; }
  .ad-3 { width: 40%; }
}
</style>
