import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('../views/Home.vue'), meta: { titleKey: 'title.home' } },
  { path: '/product', name: 'product', component: () => import('../views/Product.vue'), meta: { titleKey: 'title.product' } },
  { path: '/studio', name: 'studio', component: () => import('../views/Studio.vue'), meta: { titleKey: 'title.studio' } },
  { path: '/console/:tab?', name: 'console', component: () => import('../views/Console.vue'), meta: { titleKey: 'title.console' } },
  { path: '/cases', name: 'cases', component: () => import('../views/Cases.vue'), meta: { titleKey: 'title.cases' } },
  { path: '/pricing', name: 'pricing', component: () => import('../views/Pricing.vue'), meta: { titleKey: 'title.pricing' } },
  { path: '/about', name: 'about', component: () => import('../views/About.vue'), meta: { titleKey: 'title.about' } },
  { path: '/contact', name: 'contact', component: () => import('../views/Contact.vue'), meta: { titleKey: 'title.contact' } },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() { return { top: 0 } }
})
