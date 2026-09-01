import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { i18n, bootstrapI18n } from './i18n'
import './styles/global.css'

// Await the reader's locale chunk before mounting — see src/i18n/index.js.
bootstrapI18n().then(() => {
  createApp(App).use(router).use(i18n).mount('#app')
})
