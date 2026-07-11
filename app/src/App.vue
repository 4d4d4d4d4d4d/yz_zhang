<script setup>
import Navbar from './components/Navbar.vue'
import Footer from './components/Footer.vue'
import CommandPalette from './components/CommandPalette.vue'
</script>

<template>
  <Navbar />
  <CommandPalette />
  <main>
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <!-- Single-element keyed wrapper: views are multi-root, and a
             transition child must have one element root or in-app
             navigation renders blank (spec 23 R1). Keyed by route NAME so
             /console/:tab switches don't remount the console shell. -->
        <div :key="String($route.name)">
          <component :is="Component" />
        </div>
      </transition>
    </router-view>
  </main>
  <Footer />
</template>
