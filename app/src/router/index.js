import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('../views/Home.vue') },
  { path: '/product', name: 'product', component: () => import('../views/Product.vue') },
  { path: '/studio', name: 'studio', component: () => import('../views/Studio.vue') },
  { path: '/cases', name: 'cases', component: () => import('../views/Cases.vue') },
  { path: '/pricing', name: 'pricing', component: () => import('../views/Pricing.vue') },
  { path: '/about', name: 'about', component: () => import('../views/About.vue') },
  { path: '/contact', name: 'contact', component: () => import('../views/Contact.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() { return { top: 0 } }
})
